import struct
from typing import Optional, Dict, Any, List, Tuple
from enum import IntEnum

class OggPageType(IntEnum):
    """Ogg页类型标志"""
    CONTINUED = 0x01      # 上一页的continuation
    BEGINNING_OF_STREAM = 0x02  # 流的开始
    END_OF_STREAM = 0x04  # 流的结束

class OpusStreamParser:
    """Ogg封装的Opus流式解析器"""
    
    def __init__(self):
        self.buffer = b''
        self.stream_serial = None
        self.page_sequence = 0
        self.header_parsed = False
        self.tags_parsed = False
        self.opus_header = None
        self.opus_tags = None
        
    def find_ogg_page(self, data: bytes, start: int = 0) -> Optional[int]:
        """查找OggS页标识的位置"""
        return data.find(b'OggS', start)
    
    def parse_ogg_page(self, data: bytes) -> Optional[Dict[str, Any]]:
        """解析Ogg页结构
        
        Ogg页格式:
        - 4 bytes: 'OggS'
        - 1 byte: version (0x00)
        - 1 byte: header_type
        - 8 bytes: granule_position
        - 4 bytes: bitstream_serial_number
        - 4 bytes: page_sequence_number
        - 4 bytes: CRC checksum
        - 1 byte: page_segments (segment数量)
        - N bytes: segment_table (每个segment的长度)
        - X bytes: payload data
        """
        if len(data) < 27:  # Ogg页头最小长度
            return None
        
        try:
            # 检查OggS标识
            if data[:4] != b'OggS':
                return None
            
            # 解析页头
            version = data[4]
            header_type = data[5]
            granule_position = struct.unpack('<Q', data[6:14])[0]
            serial_number = struct.unpack('<I', data[14:18])[0]
            page_sequence = struct.unpack('<I', data[18:22])[0]
            checksum = struct.unpack('<I', data[22:26])[0]
            page_segments = data[26]
            
            # 检查是否有完整的segment table
            if len(data) < 27 + page_segments:
                return None
            
            # 读取segment table
            segment_table = list(data[27:27 + page_segments])
            
            # 计算payload大小
            payload_size = sum(segment_table)
            header_size = 27 + page_segments
            
            # 检查是否有完整的payload
            if len(data) < header_size + payload_size:
                return None
            
            # 提取payload
            payload = data[header_size:header_size + payload_size]
            
            # 解析segments (连续的255表示一个大packet)
            packets = []
            current_packet = b''
            
            for seg_size in segment_table:
                current_packet += payload[:seg_size]
                payload = payload[seg_size:]
                
                # 如果segment不是255，说明packet结束
                if seg_size < 255:
                    packets.append(current_packet)
                    current_packet = b''
            
            # 如果还有未完成的packet (最后一个segment是255)
            continued = len(current_packet) > 0
            if continued:
                packets.append(current_packet)
            
            return {
                'version': version,
                'header_type': header_type,
                'is_continued': bool(header_type & OggPageType.CONTINUED),
                'is_bos': bool(header_type & OggPageType.BEGINNING_OF_STREAM),
                'is_eos': bool(header_type & OggPageType.END_OF_STREAM),
                'granule_position': granule_position,
                'serial_number': serial_number,
                'page_sequence': page_sequence,
                'checksum': checksum,
                'page_segments': page_segments,
                'segment_table': segment_table,
                'payload_size': payload_size,
                'packets': packets,
                'packet_continued': continued,
                'total_size': header_size + payload_size
            }
        except Exception as e:
            print(f"解析Ogg页失败: {e}")
            return None
    
    def parse_opus_header(self, data: bytes) -> Optional[Dict[str, Any]]:
        """解析OpusHead"""
        if len(data) < 19:
            return None
        
        try:
            if data[:8] != b'OpusHead':
                return None
            
            version = data[8]
            channels = data[9]
            pre_skip = struct.unpack('<H', data[10:12])[0]
            sample_rate = struct.unpack('<I', data[12:16])[0]
            output_gain = struct.unpack('<h', data[16:18])[0]
            mapping_family = data[18]
            
            header_info = {
                'version': version,
                'channels': channels,
                'pre_skip': pre_skip,
                'sample_rate': sample_rate,
                'output_gain': output_gain,
                'mapping_family': mapping_family
            }
            
            # 解析channel mapping (如果有)
            if mapping_family > 0 and len(data) >= 21:
                stream_count = data[19]
                coupled_count = data[20]
                header_info['stream_count'] = stream_count
                header_info['coupled_count'] = coupled_count
                
                if len(data) >= 21 + channels:
                    header_info['channel_mapping'] = list(data[21:21 + channels])
            
            return header_info
        except Exception as e:
            print(f"解析OpusHead失败: {e}")
            return None
    
    def parse_opus_tags(self, data: bytes) -> Optional[Dict[str, Any]]:
        """解析OpusTags"""
        if len(data) < 8:
            return None
        
        try:
            if data[:8] != b'OpusTags':
                return None
            
            offset = 8
            
            # 读取vendor string长度
            if len(data) < offset + 4:
                return None
            vendor_length = struct.unpack('<I', data[offset:offset + 4])[0]
            offset += 4
            
            # 读取vendor string
            if len(data) < offset + vendor_length:
                return None
            vendor_string = data[offset:offset + vendor_length].decode('utf-8', errors='ignore')
            offset += vendor_length
            
            # 读取comment数量
            if len(data) < offset + 4:
                return None
            comment_count = struct.unpack('<I', data[offset:offset + 4])[0]
            offset += 4
            
            # 读取comments
            comments = []
            for _ in range(comment_count):
                if len(data) < offset + 4:
                    break
                comment_length = struct.unpack('<I', data[offset:offset + 4])[0]
                offset += 4
                
                if len(data) < offset + comment_length:
                    break
                comment = data[offset:offset + comment_length].decode('utf-8', errors='ignore')
                comments.append(comment)
                offset += comment_length
            
            return {
                'vendor': vendor_string,
                'comments': comments,
                'comment_count': len(comments)
            }
        except Exception as e:
            print(f"解析OpusTags失败: {e}")
            return None
    
    def get_frame_duration(self, config: int) -> float:
        """根据config获取帧时长(毫秒)
        
        Opus config到帧时长的映射表
        """
        # SILK模式 (0-11): 10, 20, 40, 60ms
        if config < 12:
            durations = [10, 20, 40, 60]
            return durations[config % 4]
        
        # Hybrid模式 (12-15): 10, 20ms
        elif config < 16:
            durations = [10, 20]
            return durations[config % 2]
        
        # CELT模式 (16-31): 2.5, 5, 10, 20ms
        else:
            durations = [2.5, 5, 10, 20]
            return durations[config % 4]
    
    def get_bandwidth_name(self, config: int) -> str:
        """获取带宽名称"""
        if config < 4:
            return "Narrowband"
        elif config < 8:
            return "Mediumband"
        elif config < 12:
            return "Wideband"
        elif config < 14:
            return "Super-wideband"
        elif config < 16:
            return "Fullband"
        elif config < 20:
            return "Narrowband"
        elif config < 24:
            return "Wideband"
        elif config < 28:
            return "Super-wideband"
        else:
            return "Fullband"
    
    def get_mode_name(self, config: int) -> str:
        """获取编码模式名称"""
        if config < 12:
            return "SILK"
        elif config < 16:
            return "Hybrid"
        else:
            return "CELT"
    
    def parse_opus_packet_info(self, data: bytes, include_raw: bool = True) -> Optional[Dict[str, Any]]:
        """解析Opus数据包的TOC信息
        
        Args:
            data: Opus packet数据
            include_raw: 是否包含原始数据（用于后续解码）
        """
        if len(data) < 1:
            return None
        
        try:
            toc = data[0]
            config = (toc >> 3) & 0x1F
            stereo_flag = (toc >> 2) & 0x01
            frame_code = toc & 0x03
            
            # 简单的帧计数估算
            frame_count_map = {0: 1, 1: 2, 2: 2, 3: 'variable'}
            frame_count = frame_count_map[frame_code]
            
            # 获取帧时长
            frame_duration_ms = self.get_frame_duration(config)
            
            # 计算packet总时长
            if frame_count == 'variable':
                packet_duration_ms = None  # 需要进一步解析
            else:
                packet_duration_ms = frame_duration_ms * frame_count
            
            result = {
                'toc': toc,
                'config': config,
                'mode': self.get_mode_name(config),
                'bandwidth': self.get_bandwidth_name(config),
                'stereo_flag': stereo_flag,
                'frame_code': frame_code,
                'frame_count': frame_count,
                'frame_duration_ms': frame_duration_ms,
                'packet_duration_ms': packet_duration_ms,
                'packet_size': len(data)
            }
            
            # 包含原始数据（用于解码）
            if include_raw:
                result['data'] = data
            
            return result
        except Exception as e:
            print(f"解析Opus包信息失败: {e}")
            return None
    
    def process_chunk(self, chunk: bytes) -> List[Dict[str, Any]]:
        """处理音频数据块，返回解析结果"""
        self.buffer += chunk
        results = []
        
        while True:
            # 查找Ogg页
            page_start = self.find_ogg_page(self.buffer)
            if page_start == -1:
                break
            
            # 如果不在开头，丢弃之前的数据
            if page_start > 0:
                print(f"⚠️  丢弃 {page_start} 字节无效数据")
                self.buffer = self.buffer[page_start:]
            
            # 尝试解析页
            page = self.parse_ogg_page(self.buffer)
            if not page:
                # 数据不完整，等待更多数据
                break
            
            # 保存stream serial
            if self.stream_serial is None:
                self.stream_serial = page['serial_number']
            
            # 处理页内容
            if page['is_bos'] and not self.header_parsed:
                # 第一页：OpusHead
                if page['packets']:
                    opus_header = self.parse_opus_header(page['packets'][0])
                    if opus_header:
                        self.opus_header = opus_header
                        self.header_parsed = True
                        results.append({
                            'type': 'header',
                            'page_info': {
                                'sequence': page['page_sequence'],
                                'granule': page['granule_position']
                            },
                            'data': opus_header
                        })
                        # print(f"✓ 解析到OpusHead: {opus_header['channels']}ch @ {opus_header['sample_rate']}Hz")
            
            elif self.header_parsed and not self.tags_parsed:
                # 第二页：OpusTags
                if page['packets']:
                    opus_tags = self.parse_opus_tags(page['packets'][0])
                    if opus_tags:
                        self.opus_tags = opus_tags
                        self.tags_parsed = True
                        results.append({
                            'type': 'tags',
                            'page_info': {
                                'sequence': page['page_sequence'],
                                'granule': page['granule_position']
                            },
                            'data': opus_tags
                        })
                        # print(f"✓ 解析到OpusTags: {opus_tags['vendor']}")
            
            elif self.header_parsed and self.tags_parsed:
                # 音频数据页
                audio_packets = []
                total_duration_ms = 0
                
                for packet in page['packets']:
                    packet_info = self.parse_opus_packet_info(packet, include_raw=True)
                    if packet_info:
                        audio_packets.append(packet_info)
                        if packet_info['packet_duration_ms']:
                            total_duration_ms += packet_info['packet_duration_ms']
                
                if audio_packets:
                    results.append({
                        'type': 'audio',
                        'page_info': {
                            'sequence': page['page_sequence'],
                            'granule': page['granule_position'],
                            'is_eos': page['is_eos']
                        },
                        'packets': audio_packets,
                        'packet_count': len(audio_packets),
                        'total_duration_ms': total_duration_ms
                    })
                    # print(f"✓ 音频页 #{page['page_sequence']}: {len(audio_packets)} 个包, "
                    #       f"时长={total_duration_ms:.1f}ms, granule={page['granule_position']}")
            
            # 移除已处理的页
            self.buffer = self.buffer[page['total_size']:]
            self.page_sequence = page['page_sequence']
            
            # 如果是流结束
            if page['is_eos']:
                results.append({
                    'type': 'eos',
                    'page_sequence': page['page_sequence']
                })
                # print("✓ 流结束")
                break
        
        return results
    
    def get_stream_info(self) -> Optional[Dict[str, Any]]:
        """获取流信息摘要"""
        if not self.header_parsed:
            return None
        
        info = {
            'header': self.opus_header,
            'serial_number': self.stream_serial,
            'current_page': self.page_sequence
        }
        
        if self.tags_parsed and self.opus_tags:
            info['tags'] = self.opus_tags
        
        return info
    
    def reset(self):
        """重置解析器"""
        self.buffer = b''
        self.stream_serial = None
        self.page_sequence = 0
        self.header_parsed = False
        self.tags_parsed = False
        self.opus_header = None
        self.opus_tags = None


# 使用示例
if __name__ == "__main__":
    parser = OpusStreamParser()
    
    # 模拟你的数据流
    test_data = (
        b'OggS\x00\x02\x00\x00\x00\x00\x00\x00\x00\x00'
        b'\xc7\xca|\x1f\x00\x00\x00\x00\x89\x9c\xe7\xd9'
        b'\x01\x13OpusHead\x01\x01\x38\x01\x80\x3e\x00\x00\x00\x00\x00'
    )
    
    # 模拟流式输入
    for i in range(0, len(test_data), 10):
        chunk = test_data[i:i+10]
        results = parser.process_chunk(chunk)
        
        for result in results:
            print(f"\n类型: {result['type']}")
            if result['type'] == 'header':
                print(f"  声道: {result['data']['channels']}")
                print(f"  采样率: {result['data']['sample_rate']} Hz")
    
    # 获取流信息
    stream_info = parser.get_stream_info()
    if stream_info:
        print("\n=== 流信息 ===")
        print(f"采样率: {stream_info['header']['sample_rate']} Hz")
        print(f"声道数: {stream_info['header']['channels']}")
        print(f"Serial: {stream_info['serial_number']}")