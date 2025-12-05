"""
WebM容器解析器 - 用于从WebM容器中提取Opus数据包

WebM格式说明：
- WebM是基于Matroska的容器格式
- Opus音频数据存储在Cluster中的SimpleBlock或Block中
- 需要解析EBML (Extensible Binary Meta Language) 结构
"""

import struct
from typing import List, Dict, Any, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


class WebMParser:
    """WebM容器解析器 - 流式解析Opus数据包"""
    
    def __init__(self):
        self.buffer = b''
        self.cluster_started = False
        self.track_number = None
        self.codec_id = None
        
    def find_ebml_element(self, data: bytes, start: int = 0) -> Optional[Tuple[int, int, int]]:
        """查找EBML元素
        返回: (element_id, element_size, element_start_pos) 或 None
        """
        if start >= len(data):
            return None
            
        # 读取Element ID (VINT编码)
        pos = start
        if pos >= len(data):
            return None
            
        # 读取第一个字节
        first_byte = data[pos]
        pos += 1
        
        # 计算ID长度（第一个字节中前导1的个数）
        id_length = 0
        mask = 0x80
        while mask > 0 and (first_byte & mask) == 0:
            id_length += 1
            mask >>= 1
        
        if id_length == 0:
            id_length = 1
        
        # 读取完整的ID
        if pos + id_length - 1 >= len(data):
            return None
            
        element_id = 0
        for i in range(id_length):
            element_id = (element_id << 8) | data[pos + i]
        pos += id_length
        
        # 读取Element Size (VINT编码)
        if pos >= len(data):
            return None
            
        size_first_byte = data[pos]
        pos += 1
        
        # 计算Size长度
        size_length = 0
        mask = 0x80
        while mask > 0 and (size_first_byte & mask) == 0:
            size_length += 1
            mask >>= 1
        
        if size_length == 0:
            size_length = 1
        
        # 读取完整的Size
        if pos + size_length - 1 >= len(data):
            return None
            
        element_size = size_first_byte & (0x7F >> (size_length - 1))
        for i in range(1, size_length):
            element_size = (element_size << 8) | data[pos + i - 1]
        pos += size_length - 1
        
        element_start = start
        return (element_id, element_size, element_start)
    
    def parse_cluster(self, data: bytes) -> List[bytes]:
        """解析Cluster，提取Opus数据包"""
        opus_packets = []
        pos = 0
        
        while pos < len(data):
            element = self.find_ebml_element(data, pos)
            if not element:
                break
                
            element_id, element_size, element_start = element
            element_end = element_start + element_size
            
            # SimpleBlock (0xA3) 或 Block (0xA1)
            if element_id == 0xA3:  # SimpleBlock
                # SimpleBlock格式: TrackNumber + Timecode + Flags + Data
                block_data = data[element_start + element_size - element_size:element_end]
                # 这里简化处理，实际需要解析TrackNumber和Timecode
                # 假设数据部分就是Opus数据包
                if len(block_data) > 4:
                    # 跳过TrackNumber (VINT) 和 Timecode (int16)
                    # 简化：直接取数据部分
                    opus_data = block_data[4:]  # 简化处理
                    if opus_data:
                        opus_packets.append(opus_data)
            elif element_id == 0xA1:  # Block
                # Block格式类似，但更复杂
                pass
            
            pos = element_end
        
        return opus_packets
    
    def process_chunk(self, data: bytes) -> List[Dict[str, Any]]:
        """处理WebM数据块，提取Opus数据包
        
        返回: List[Dict] 包含提取的Opus数据包信息
        """
        results = []
        self.buffer += data
        
        # 查找Cluster (0x1F43B675)
        cluster_id = 0x1F43B675
        
        while True:
            # 查找Cluster开始位置
            cluster_pos = self.buffer.find(b'\x1F\x43\xB6\x75', 0)
            if cluster_pos == -1:
                break
            
            # 解析Cluster
            element = self.find_ebml_element(self.buffer, cluster_pos)
            if not element:
                break
                
            element_id, element_size, element_start = element
            element_end = element_start + element_size
            
            if element_id == cluster_id and element_end <= len(self.buffer):
                # 提取Cluster数据
                cluster_data = self.buffer[element_start:element_end]
                opus_packets = self.parse_cluster(cluster_data)
                
                for opus_packet in opus_packets:
                    results.append({
                        'type': 'audio',
                        'data': opus_packet,
                        'packet_duration_ms': 60.0  # 假设60ms，实际需要从时间戳计算
                    })
                
                # 移除已处理的数据
                self.buffer = self.buffer[element_end:]
            else:
                break
        
        return results

