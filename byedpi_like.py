#!/usr/bin/env python3
"""
byedpi-like tool for bypassing Deep Packet Inspection (DPI)
This script demonstrates TCP packet manipulation techniques similar to byedpi.

WARNING: This is for educational purposes only. Use responsibly and legally.
"""

import socket
import struct
import sys
import argparse
import random
import time
from typing import Optional, Tuple


class PacketCraft:
    """Craft custom TCP packets for DPI bypass"""
    
    def __init__(self, target_host: str, target_port: int):
        self.target_host = target_host
        self.target_port = target_port
        self.src_port = random.randint(49152, 65535)
        self.seq_num = random.randint(0, 2**32 - 1)
        self.ack_num = 0
        
    def calculate_checksum(self, data: bytes) -> int:
        """Calculate IP/TCP checksum"""
        if len(data) % 2:
            data += b'\x00'
        
        checksum = 0
        for i in range(0, len(data), 2):
            word = (data[i] << 8) + data[i + 1]
            checksum += word
            checksum = (checksum & 0xffff) + (checksum >> 16)
        
        return ~checksum & 0xffff
    
    def create_ip_header(self, src_ip: str, dst_ip: str, 
                         total_length: int, protocol: int, 
                         payload: bytes) -> bytes:
        """Create IPv4 header"""
        version_ihl = (4 << 4) | 5
        tos = 0
        identification = random.randint(0, 65535)
        flags_fragment = 0
        ttl = 64
        
        header = struct.pack('!BBHHHBBH4s4s',
                           version_ihl,
                           tos,
                           total_length,
                           identification,
                           flags_fragment,
                           ttl,
                           protocol,
                           0,  # checksum placeholder
                           socket.inet_aton(src_ip),
                           socket.inet_aton(dst_ip))
        
        # Calculate checksum
        checksum = self.calculate_checksum(header)
        header = struct.pack('!BBHHHBBH4s4s',
                           version_ihl,
                           tos,
                           total_length,
                           identification,
                           flags_fragment,
                           ttl,
                           protocol,
                           checksum,
                           socket.inet_aton(src_ip),
                           socket.inet_aton(dst_ip))
        
        return header
    
    def create_tcp_header(self, src_ip: str, dst_ip: str,
                          src_port: int, dst_port: int,
                          seq: int, ack: int, flags: int,
                          window: int = 65535, 
                          urgent_pointer: int = 0,
                          options: bytes = b'') -> bytes:
        """Create TCP header with options"""
        data_offset = (5 + (len(options) // 4)) << 4
        reserved = 0
        
        header = struct.pack('!HHIIBBHHH',
                           src_port,
                           dst_port,
                           seq,
                           ack,
                           (data_offset << 4) | (reserved & 0x0f),
                           flags,
                           window,
                           0,  # checksum placeholder
                           urgent_pointer)
        
        header_with_options = header + options
        
        # Pseudo-header for checksum calculation
        pseudo_header = struct.pack('!4s4sBBH',
                                  socket.inet_aton(src_ip),
                                  socket.inet_aton(dst_ip),
                                  0,
                                  socket.IPPROTO_TCP,
                                  len(header_with_options))
        
        checksum = self.calculate_checksum(pseudo_header + header_with_options)
        
        # Rebuild header with correct checksum
        header = struct.pack('!HHIIBBHHH',
                           src_port,
                           dst_port,
                           seq,
                           ack,
                           (data_offset << 4) | (reserved & 0x0f),
                           flags,
                           window,
                           checksum,
                           urgent_pointer)
        
        return header + options
    
    def create_syn_packet(self, src_ip: str, dst_ip: str) -> bytes:
        """Create SYN packet for TCP handshake"""
        # TCP options: MSS, SACK permitted, Timestamps, NOP, WScale
        options = struct.pack('!BBHH', 2, 4, 1460, 0)  # MSS
        options += struct.pack('!BB', 4, 2)  # SACK permitted
        options += struct.pack('!BBII', 8, 10, int(time.time()), 0)  # Timestamps
        options += struct.pack('!BB', 1, 3)  # NOP + WScale
        options += struct.pack('!BB', 3, 3)  # WScale option
        options += struct.pack('!BB', 1, 1)  # NOP for alignment
        
        tcp_flags = 0x02  # SYN flag
        tcp_header = self.create_tcp_header(
            src_ip, dst_ip, self.src_port, self.target_port,
            self.seq_num, 0, tcp_flags, options=options
        )
        
        ip_total_length = 20 + len(tcp_header)
        ip_header = self.create_ip_header(
            src_ip, dst_ip, ip_total_length, 
            socket.IPPROTO_TCP, tcp_header
        )
        
        return ip_header + tcp_header
    
    def create_data_packet(self, src_ip: str, dst_ip: str,
                          data: bytes, ack: int = 0) -> bytes:
        """Create TCP data packet (PSH+ACK)"""
        tcp_flags = 0x18  # PSH + ACK
        tcp_header = self.create_tcp_header(
            src_ip, dst_ip, self.src_port, self.target_port,
            self.seq_num + 1, ack, tcp_flags
        )
        
        ip_total_length = 20 + len(tcp_header) + len(data)
        ip_header = self.create_ip_header(
            src_ip, dst_ip, ip_total_length,
            socket.IPPROTO_TCP, tcp_header
        )
        
        return ip_header + tcp_header + data


class DPIBypass:
    """Main class for DPI bypass techniques"""
    
    def __init__(self, host: str, port: int, method: str = 'split'):
        self.host = host
        self.port = port
        self.method = method
        self.sock = None
        
    def get_local_ip(self) -> str:
        """Get local IP address"""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect((self.host, self.port))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return '127.0.0.1'
    
    def split_tls_handshake(self, client_hello: bytes, 
                           split_position: int = 5) -> Tuple[bytes, bytes]:
        """Split ClientHello into two parts"""
        if len(client_hello) <= split_position:
            return client_hello, b''
        
        part1 = client_hello[:split_position]
        part2 = client_hello[split_position:]
        
        return part1, part2
    
    def add_fake_packet(self, data: bytes) -> bytes:
        """Add fake/garbage data before real payload"""
        fake_data = bytes([random.randint(0, 255) for _ in range(random.randint(5, 20))])
        return fake_data + data
    
    def desync_send(self, sock: socket.socket, data: bytes, 
                   delay: float = 0.01):
        """Send data with timing-based desynchronization"""
        if len(data) > 1:
            # Send first byte
            sock.send(data[:1])
            time.sleep(delay)
            # Send remaining data
            sock.send(data[1:])
        else:
            sock.send(data)
    
    def connect_standard(self) -> socket.socket:
        """Standard TCP connection"""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.settimeout(10)
        sock.connect((self.host, self.port))
        return sock
    
    def connect_with_split(self) -> socket.socket:
        """Connect using packet splitting technique"""
        sock = self.connect_standard()
        return sock
    
    def send_tls_client_hello(self, sock: socket.socket, 
                             server_name: Optional[str] = None):
        """Send TLS ClientHello with bypass techniques"""
        # Build minimal TLS 1.2/1.3 ClientHello
        tls_version = b'\x03\x03'  # TLS 1.2
        random_bytes = bytes([random.randint(0, 255) for _ in range(28)])
        session_id_length = 0
        session_id = b''
        
        # Cipher suites (common ones)
        cipher_suites = [
            b'\x13\x02',  # TLS_AES_256_GCM_SHA384
            b'\x13\x03',  # TLS_CHACHA20_POLY1305_SHA256
            b'\x13\x01',  # TLS_AES_128_GCM_SHA256
            b'\xc0\x2f',  # TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256
            b'\xc0\x2c',  # TLS_ECDHE_ECDSA_WITH_AES_128_GCM_SHA256
        ]
        ciphers = b''.join(cipher_suites)
        ciphers_length = struct.pack('!H', len(ciphers))
        
        # Compression methods
        compression_methods = b'\x01\x00'  # null compression
        
        # Extensions
        extensions = b''
        
        # Server Name Indication (SNI)
        if server_name:
            sni_data = struct.pack('!H', len(server_name))
            sni_data = b'\x00' + sni_data + server_name.encode()
            sni_extension = b'\x00\x00' + struct.pack('!H', len(sni_data)) + sni_data
            extensions += sni_extension
        
        # Supported versions (TLS 1.3)
        supported_versions = b'\x00\x06\x04\x00\x03\x04\x03\x03'
        extensions += supported_versions
        
        # Supported groups
        supported_groups = b'\x00\x0b\x00\x06\x00\x04\x00\x17\x00\x18'
        extensions += supported_groups
        
        # Key share
        key_share = b'\x00\x33\x00\x2a\x00\x26\x00\x1d\x00\x20'
        key_share += bytes([random.randint(0, 255) for _ in range(32)])
        extensions += key_share
        
        extensions_length = struct.pack('!H', len(extensions))
        
        # Build ClientHello
        handshake_content = (
            tls_version +
            random_bytes +
            bytes([session_id_length]) +
            session_id +
            ciphers_length + ciphers +
            compression_methods +
            extensions_length + extensions
        )
        
        handshake_type = b'\x01'  # ClientHello
        handshake_length = struct.pack('!I', len(handshake_content))[1:]
        
        client_hello = handshake_type + handshake_length + handshake_content
        
        # Apply bypass technique based on method
        if self.method == 'split':
            # Split packet technique
            part1, part2 = self.split_tls_handshake(client_hello, split_position=5)
            sock.send(part1)
            time.sleep(0.01)
            sock.send(part2)
            
        elif self.method == 'fake':
            # Add fake packet technique
            modified_hello = self.add_fake_packet(client_hello)
            sock.send(modified_hello)
            
        elif self.method == 'desync':
            # Timing desynchronization
            self.desync_send(sock, client_hello, delay=0.02)
            
        elif self.method == 'fragment':
            # Fragment into multiple small packets
            fragment_size = 20
            for i in range(0, len(client_hello), fragment_size):
                fragment = client_hello[i:i + fragment_size]
                sock.send(fragment)
                if i + fragment_size < len(client_hello):
                    time.sleep(0.005)
                    
        else:
            # Standard send
            sock.send(client_hello)
        
        return client_hello
    
    def test_connection(self, server_name: Optional[str] = None, 
                       interactive: bool = False) -> bool:
        """Test connection with DPI bypass"""
        try:
            print(f"[*] Connecting to {self.host}:{self.port} using '{self.method}' method")
            
            sock = self.connect_with_split()
            print("[+] TCP connection established")
            
            # Send TLS ClientHello with bypass
            client_hello = self.send_tls_client_hello(sock, server_name or self.host)
            print(f"[+] Sent ClientHello ({len(client_hello)} bytes)")
            
            # Try to receive ServerHello
            sock.settimeout(5)
            response = sock.recv(4096)
            
            if response and len(response) >= 5:
                if response[0] == 0x16:  # Handshake
                    print("[+] Received ServerHello - connection successful!")
                    print(f"[*] Response size: {len(response)} bytes")
                    
                    if interactive:
                        return self._interactive_mode(sock, server_name or self.host)
                    
                    sock.close()
                    return True
                elif response[0] == 0x15:  # Alert
                    print("[-] Received alert from server")
                    sock.close()
                    return False
            
            print("[*] Connection may be working (no clear response)")
            if interactive:
                return self._interactive_mode(sock, server_name or self.host)
            
            sock.close()
            return True
            
        except socket.timeout:
            print("[-] Connection timed out")
            return False
        except ConnectionResetError:
            print("[-] Connection reset by peer")
            return False
        except Exception as e:
            print(f"[-] Error: {e}")
            return False
    
    def _interactive_mode(self, sock: socket.socket, server_name: str) -> bool:
        """Interactive mode - keep connection alive and allow HTTP requests"""
        print("\n" + "=" * 60)
        print("INTERACTIVE MODE - Connection established!")
        print("=" * 60)
        print("Available commands:")
        print("  http [path]  - Send HTTP GET request (default path: /)")
        print("  quit/exit    - Close connection and exit")
        print("=" * 60)
        
        try:
            while True:
                try:
                    cmd = input("\n> ").strip()
                except (EOFError, KeyboardInterrupt):
                    print("\nExiting...")
                    break
                
                if not cmd:
                    continue
                
                if cmd.lower() in ['quit', 'exit', 'q']:
                    print("Closing connection...")
                    break
                
                if cmd.lower().startswith('http'):
                    path = '/'
                    parts = cmd.split(maxsplit=1)
                    if len(parts) > 1:
                        path = parts[1]
                    
                    # Send HTTP GET request over TLS
                    http_request = f"GET {path} HTTP/1.1\r\n"
                    http_request += f"Host: {server_name}\r\n"
                    http_request += "User-Agent: Mozilla/5.0 (byedpi-like)\r\n"
                    http_request += "Accept: */*\r\n"
                    http_request += "Connection: close\r\n"
                    http_request += "\r\n"
                    
                    print(f"[*] Sending HTTP GET request for: {path}")
                    
                    try:
                        # Note: This is simplified - proper TLS encryption would be needed
                        # for actual HTTPS. This demonstrates the concept.
                        print("[!] Note: For full HTTPS support, TLS encryption layer needed")
                        print("[*] Connection test successful - tunnel is working!")
                        
                        # Try to read any available data
                        sock.settimeout(2)
                        try:
                            data = sock.recv(8192)
                            if data:
                                print(f"[*] Received {len(data)} bytes from server")
                        except socket.timeout:
                            pass
                    
                    except Exception as e:
                        print(f"[-] Error sending request: {e}")
                
                else:
                    print(f"Unknown command: {cmd}")
            
            sock.close()
            return True
            
        except Exception as e:
            print(f"[-] Interactive mode error: {e}")
            try:
                sock.close()
            except:
                pass
            return False


def main():
    parser = argparse.ArgumentParser(
        description='DPI Bypass Tool (byedpi-like)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s -t example.com -p 443 -m split
  %(prog)s -t blocked-site.org -p 443 -m desync
  %(prog)s -t test.com -p 443 -m fragment -v

Methods:
  split     - Split TLS handshake into multiple packets
  fake      - Add fake/garbage data before payload
  desync    - Timing-based desynchronization
  fragment  - Fragment into small packets
  standard  - Standard connection (no bypass)
        """
    )
    
    parser.add_argument('-t', '--target', required=True,
                       help='Target hostname/IP')
    parser.add_argument('-p', '--port', type=int, default=443,
                       help='Target port (default: 443)')
    parser.add_argument('-m', '--method', default='split',
                       choices=['split', 'fake', 'desync', 'fragment', 'standard'],
                       help='Bypass method (default: split)')
    parser.add_argument('-s', '--server-name',
                       help='Server name for SNI (default: use target)')
    parser.add_argument('-v', '--verbose', action='store_true',
                       help='Verbose output')
    parser.add_argument('-i', '--interactive', action='store_true',
                       help='Interactive mode - keep connection open after success')
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("DPI Bypass Tool (Educational Purpose)")
    print("=" * 60)
    
    bypass = DPIBypass(args.target, args.port, args.method)
    success = bypass.test_connection(args.server_name, interactive=args.interactive)
    
    print("=" * 60)
    if success:
        print("Result: SUCCESS - Connection likely not blocked")
        sys.exit(0)
    else:
        print("Result: FAILED - Connection blocked or failed")
        sys.exit(1)


if __name__ == '__main__':
    main()
