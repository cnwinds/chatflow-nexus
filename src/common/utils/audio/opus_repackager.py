"""Opus数据重打包器 - 保持Opus格式，支持静音填充"""

import opuslib_next
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

@dataclass
class OpusChunk:
    """重打包后的Opus数据块"""
    opus_data: bytes         # Opus压缩格式数据
    duration_ms: float       # 时长(毫秒)
    sample_rate: int         # 采样率
    channels: int            # 声道数
    original_packet_count: int  # 原始packet数量
    is_padded: bool = False  # 是否包含静音填充
    
    @property
    def sample_count(self) -> int:
        """样本数量"""
        return int(self.duration_ms * self.sample_rate / 1000)
    
    @property
    def size_bytes(self) -> int:
        """数据大小(字节)"""
        return len(self.opus_data)
    
    def to_dict(self) -> Dict[str, Any]:
        """转为字典"""
        return {
            'opus_data': self.opus_data,
            'duration_ms': self.duration_ms,
            'sample_rate': self.sample_rate,
            'channels': self.channels,
            'sample_count': self.sample_count,
            'size_bytes': self.size_bytes,
            'original_packet_count': self.original_packet_count,
            'is_padded': self.is_padded
        }


class OpusRepackager:
    """Opus数据重打包器
    
    功能:
    - 将多个小的Opus packet合并为指定时长的chunk
    - 保持Opus压缩格式(适合网络传输)
    - 不足目标时长时自动填充静音
    - 完全流式处理
    
    工作流程:
    1. 解码原始Opus packets为PCM
    2. 合并PCM数据(必要时填充静音)
    3. 重新编码为单个Opus packet
    """
    
    def __init__(
        self,
        sample_rate: int = 16000,
        channels: int = 1,
        target_chunk_ms: float = 60.0,
        opus_bitrate: int = 24000,
        opus_application: str = 'voip'  # 'voip', 'audio', 'restricted_lowdelay'
    ):
        """
        Args:
            sample_rate: 采样率 (8000, 12000, 16000, 24000, 48000)
            channels: 声道数 (1 or 2)
            target_chunk_ms: 目标chunk时长(毫秒)，必须是2.5的倍数
            opus_bitrate: 编码比特率 (6000-510000)
            opus_application: 应用类型
        """
        self.sample_rate = sample_rate
        self.channels = channels
        self.target_chunk_ms = target_chunk_ms
        self.opus_bitrate = opus_bitrate
        
        # 验证时长是有效的Opus帧长
        valid_durations = [2.5, 5, 10, 20, 40, 60]
        if target_chunk_ms not in valid_durations:
            print(f"⚠️  警告: {target_chunk_ms}ms 不是标准Opus帧长，"
                  f"建议使用: {valid_durations}")
        
        # Opus解码器
        self.decoder = opuslib_next.Decoder(sample_rate, channels)
        
        # Opus编码器 (opuslib_next 使用字符串参数)
        self.encoder = opuslib_next.Encoder(
            sample_rate, 
            channels, 
            opus_application  # 'voip', 'audio', 'restricted_lowdelay'
        )
        self.encoder.bitrate = opus_bitrate
        
        # 缓冲区
        self.pending_packets: List[Dict[str, Any]] = []
        self.accumulated_duration: float = 0.0
        
        # 统计
        self.total_input_packets = 0
        self.total_output_chunks = 0
        self.total_duration_processed = 0.0
        self.total_padded_chunks = 0
    
    def add_packet(self, packet_info: Dict[str, Any]) -> List[OpusChunk]:
        """添加一个Opus packet
        
        Args:
            packet_info: 包含以下字段的字典:
                - 'data': bytes - Opus压缩数据
                - 'packet_duration_ms': float - packet时长
                - 其他可选字段(用于调试)
        
        Returns:
            已完成的chunk列表(可能为空)
        """
        self.pending_packets.append(packet_info)
        self.accumulated_duration += packet_info.get('packet_duration_ms', 20.0)
        self.total_input_packets += 1
        
        # 检查是否达到目标时长
        if self.accumulated_duration >= self.target_chunk_ms:
            return self._flush(pad_to_target=False)
        
        return []
    
    def finalize(self) -> List[OpusChunk]:
        """完成处理，返回所有剩余的chunk(自动填充到目标时长)
        
        Returns:
            剩余的chunk列表
        """
        return self._flush(pad_to_target=True)
    
    def _flush(self, pad_to_target: bool = False) -> List[OpusChunk]:
        """刷新缓冲区，生成chunk
        
        Args:
            pad_to_target: 是否填充到目标时长
        
        Returns:
            生成的chunk列表
        """
        if not self.pending_packets:
            return []
        
        chunks = []
        
        try:
            # 计算需要处理的packets
            packets_to_process = []
            remaining_packets = []
            accumulated = 0.0
            
            for packet in self.pending_packets:
                duration = packet.get('packet_duration_ms', 20.0)
                
                # 如果添加这个packet会超过目标时长太多，保留到下次
                if accumulated > 0 and accumulated + duration > self.target_chunk_ms * 1.2:
                    remaining_packets.append(packet)
                else:
                    packets_to_process.append(packet)
                    accumulated += duration
            
            # 生成chunk
            if packets_to_process:
                chunk = self._process_packets(
                    packets_to_process, 
                    accumulated,
                    pad_to_target
                )
                if chunk:
                    chunks.append(chunk)
                    self.total_output_chunks += 1
                    self.total_duration_processed += chunk.duration_ms
                    if chunk.is_padded:
                        self.total_padded_chunks += 1
            
            # 更新缓冲区
            self.pending_packets = remaining_packets
            self.accumulated_duration = sum(
                p.get('packet_duration_ms', 20.0) for p in remaining_packets
            )
            
        except Exception as e:
            print(f"❌ 重打包失败: {e}")
            import traceback
            traceback.print_exc()
            # 发生错误时清空缓冲区
            self.pending_packets = []
            self.accumulated_duration = 0.0
        
        return chunks
    
    def _process_packets(
        self, 
        packets: List[Dict[str, Any]], 
        total_duration: float,
        pad_to_target: bool
    ) -> Optional[OpusChunk]:
        """处理多个packet并重新编码为一个Opus chunk
        
        Args:
            packets: packet列表
            total_duration: 总时长
            pad_to_target: 是否填充到目标时长
        
        Returns:
            重新编码的chunk
        """
        # 1. 解码所有packets为PCM
        pcm_chunks = []
        actual_duration = 0.0
        
        for packet in packets:
            duration_ms = packet.get('packet_duration_ms', 20.0)
            frame_size = int(duration_ms * self.sample_rate / 1000)
            
            try:
                pcm = self.decoder.decode(packet['data'], frame_size)
                pcm_chunks.append(pcm)
                actual_duration += duration_ms
            except Exception as e:
                print(f"⚠️  解码packet失败: {e}")
                continue
        
        if not pcm_chunks:
            return None
        
        # 2. 合并PCM数据
        merged_pcm = b''.join(pcm_chunks)
        
        # 3. 检查是否需要填充
        is_padded = False
        target_duration = self.target_chunk_ms
        
        if pad_to_target and actual_duration < target_duration:
            # 计算需要填充的样本数
            padding_duration_ms = target_duration - actual_duration
            padding_samples = int(padding_duration_ms * self.sample_rate / 1000)
            
            # 生成静音数据 (16-bit PCM)
            silence = b'\x00\x00' * padding_samples * self.channels
            merged_pcm += silence
            
            actual_duration = target_duration
            is_padded = True
            
            # print(f"🔇 填充静音: {padding_duration_ms:.1f}ms "
            #       f"({padding_samples} samples)")
        
        # 4. 重新编码为Opus
        try:
            # 计算编码的frame_size
            frame_size = int(actual_duration * self.sample_rate / 1000)
            
            # 编码
            opus_data = self.encoder.encode(merged_pcm, frame_size)
            
            # print(f"✓ 重编码: {actual_duration:.1f}ms, "
            #       f"{len(packets)}个包 → {len(opus_data)}字节Opus"
            #       f"{' (含填充)' if is_padded else ''}")
            
            return OpusChunk(
                opus_data=opus_data,
                duration_ms=actual_duration,
                sample_rate=self.sample_rate,
                channels=self.channels,
                original_packet_count=len(packets),
                is_padded=is_padded
            )
            
        except Exception as e:
            print(f"❌ Opus编码失败: {e}")
            return None
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            'input_packets': self.total_input_packets,
            'output_chunks': self.total_output_chunks,
            'padded_chunks': self.total_padded_chunks,
            'duration_processed_ms': self.total_duration_processed,
            'pending_packets': len(self.pending_packets),
            'pending_duration_ms': self.accumulated_duration,
            'average_chunk_ms': (
                self.total_duration_processed / self.total_output_chunks
                if self.total_output_chunks > 0 else 0
            ),
            'compression_ratio': (
                self.total_input_packets / self.total_output_chunks
                if self.total_output_chunks > 0 else 0
            )
        }
    
    def reset(self) -> None:
        """重置重打包器状态"""
        self.pending_packets = []
        self.accumulated_duration = 0.0
    
    def reset_stats(self) -> None:
        """重置统计信息"""
        self.total_input_packets = 0
        self.total_output_chunks = 0
        self.total_duration_processed = 0.0
        self.total_padded_chunks = 0
    
    def close(self) -> None:
        """关闭编解码器并清理资源"""
        try:
            # 清理编码器和解码器
            if hasattr(self, 'encoder') and self.encoder:
                del self.encoder
                self.encoder = None
            if hasattr(self, 'decoder') and self.decoder:
                del self.decoder
                self.decoder = None
            
            # 清空缓冲区
            if hasattr(self, 'pending_packets'):
                self.pending_packets.clear()
            
            # 重置状态
            self.reset()
            self.reset_stats()
        except Exception as e:
            print(f"关闭OpusRepackager失败: {e}")


# ============= 使用示例 =============

def example_basic_usage():
    """基础使用示例"""
    print("=== 示例1: 基础使用 ===\n")
    
    # 创建重打包器: 将20ms的packet重打包为60ms的Opus chunk
    repackager = OpusRepackager(
        sample_rate=16000,
        channels=1,
        target_chunk_ms=60.0,
        opus_bitrate=24000
    )
    
    # 模拟接收到的packets (真实场景从 OpusStreamParser 获取)
    # 注意: 这里需要真实的Opus数据，下面仅为示例结构
    mock_packets = [
        {'data': b'\xb8' + b'\x00' * 159, 'packet_duration_ms': 20.0},
        {'data': b'\xb8' + b'\x00' * 159, 'packet_duration_ms': 20.0},
        {'data': b'\xb8' + b'\x00' * 159, 'packet_duration_ms': 20.0},
        {'data': b'\xb8' + b'\x00' * 159, 'packet_duration_ms': 20.0},
        {'data': b'\xb8' + b'\x00' * 159, 'packet_duration_ms': 20.0},
    ]
    
    print("逐个添加packet:")
    for i, packet in enumerate(mock_packets, 1):
        print(f"  添加packet #{i} (20ms)")
        chunks = repackager.add_packet(packet)
        
        # 处理返回的chunk
        for chunk in chunks:
            print(f"  📦 输出chunk: {chunk.duration_ms:.1f}ms, "
                  f"{chunk.size_bytes}字节Opus, "
                  f"来自{chunk.original_packet_count}个packet")
            # 通过网络发送
            send_opus_over_network(chunk.opus_data)
    
    # 处理剩余数据(自动填充到60ms)
    print("\n完成处理:")
    final_chunks = repackager.finalize()
    for chunk in final_chunks:
        print(f"  📦 最终chunk: {chunk.duration_ms:.1f}ms, "
              f"{chunk.size_bytes}字节"
              f"{' (已填充)' if chunk.is_padded else ''}")
        send_opus_over_network(chunk.opus_data)
    
    # 统计信息
    stats = repackager.get_stats()
    print(f"\n📊 统计:")
    print(f"  输入: {stats['input_packets']} 个packet")
    print(f"  输出: {stats['output_chunks']} 个chunk")
    print(f"  填充: {stats['padded_chunks']} 个chunk")
    print(f"  压缩比: {stats['compression_ratio']:.1f}:1")


def send_opus_over_network(opus_data: bytes):
    """模拟网络发送Opus数据"""
    # 实际实现:
    # websocket.send(opus_data)
    # 或
    # udp_socket.sendto(opus_data, address)
    # 或
    # http_response.write(opus_data)
    pass


def example_with_parser():
    """结合OpusStreamParser的完整示例"""
    print("\n=== 示例2: 完整流程 ===\n")
    
    from opus_stream_parser import OpusStreamParser
    
    parser = OpusStreamParser()
    repackager = OpusRepackager(
        sample_rate=16000,
        channels=1,
        target_chunk_ms=60.0,
        opus_bitrate=24000
    )
    
    def process_opus_stream(stream_data: bytes):
        """处理Opus流数据"""
        results = parser.process_chunk(stream_data)
        
        for result in results:
            if result['type'] == 'header':
                print(f"📋 音频参数: {result['data']['channels']}ch "
                      f"@ {result['data']['sample_rate']}Hz")
            
            elif result['type'] == 'audio':
                print(f"🎵 收到 {result['packet_count']} 个packets, "
                      f"总时长 {result.get('total_duration_ms', 0):.1f}ms")
                
                # 重打包
                for packet in result['packets']:
                    chunks = repackager.add_packet(packet)
                    
                    # 发送生成的chunks
                    for chunk in chunks:
                        print(f"  📡 发送chunk: {chunk.duration_ms:.1f}ms, "
                              f"{chunk.size_bytes}字节")
                        send_opus_over_network(chunk.opus_data)
            
            elif result['type'] == 'eos':
                print("🏁 流结束")
                final_chunks = repackager.finalize()
                for chunk in final_chunks:
                    print(f"  📡 发送最终chunk: {chunk.duration_ms:.1f}ms")
                    send_opus_over_network(chunk.opus_data)
    
    # 使用
    print("模拟流式处理:")
    # with open('audio.opus', 'rb') as f:
    #     while chunk := f.read(4096):
    #         process_opus_stream(chunk)


def example_network_scenarios():
    """不同网络场景示例"""
    print("\n=== 示例3: 不同网络场景 ===\n")
    
    scenarios = [
        (40, "WebRTC实时通话", 32000),
        (60, "一般流媒体", 24000),
        (100, "低带宽场景", 16000),
    ]
    
    for target_ms, desc, bitrate in scenarios:
        print(f"\n{desc}:")
        print(f"  目标帧长: {target_ms}ms")
        print(f"  比特率: {bitrate}bps")
        
        repackager = OpusRepackager(
            target_chunk_ms=target_ms,
            opus_bitrate=bitrate
        )
        
        # 模拟处理
        # ...


if __name__ == "__main__":
    print("Opus重打包器示例\n")
    print("=" * 50)
    
    try:
        example_basic_usage()
        
        # 如果有真实的Opus流，可以运行:
        # example_with_parser()
        
    except Exception as e:
        print(f"\n❌ 示例运行失败: {e}")
        print("\n需要安装:")
        print("  pip install opuslib-next")
        print("\n注意:")
        print("  - 示例中的mock数据不是真实的Opus packet")
        print("  - 实际使用需要从OpusStreamParser获取真实数据")