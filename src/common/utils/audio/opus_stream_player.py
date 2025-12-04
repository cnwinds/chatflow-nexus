"""Opus流式播放器 - 基于OpusRepackager重构"""

import queue
import threading
import time
from typing import Dict, List, Any, Optional, Callable
from opus_repackager import OpusRepackager, OpusChunk

class OpusStreamPlayer:
    """Opus流式播放器 - 基于OpusRepackager重构
    
    特性:
    - 使用OpusRepackager进行数据重打包
    - 线程安全的播放控制
    - 支持播放状态管理
    - 支持自定义播放回调
    """
    
    def __init__(
        self, 
        sample_rate: int = 16000,
        channels: int = 1,
        target_chunk_ms: float = 60.0,
        max_buffer_chunks: int = 10,
        audio_callback: Optional[Callable] = None
    ):
        """
        Args:
            sample_rate: 采样率
            channels: 声道数
            target_chunk_ms: 目标chunk时长(ms)
            max_buffer_chunks: 最大缓冲chunk数量
            audio_callback: 音频数据回调函数 callback(pcm_data, sample_rate, channels)
        """
        self.sample_rate = sample_rate
        self.channels = channels
        self.max_buffer_chunks = max_buffer_chunks
        self.audio_callback = audio_callback
        
        # 使用OpusRepackager进行数据重打包
        self.repackager = OpusRepackager(
            sample_rate=sample_rate,
            channels=channels,
            target_chunk_ms=target_chunk_ms,
            allow_partial=True  # 允许部分chunk用于播放
        )
        
        # 播放控制
        self.playback_queue = queue.Queue(maxsize=max_buffer_chunks)
        self.is_running = False
        self.is_paused = False
        self.playback_thread = None
        
        # 统计信息
        self.total_packets_received = 0
        self.total_chunks_played = 0
        self.total_duration_played = 0.0
    
    def add_packet(self, packet_info: Dict[str, Any]) -> None:
        """添加Opus packet
        
        Args:
            packet_info: 包含'data'和'packet_duration_ms'的字典
        """
        self.total_packets_received += 1
        
        # 使用repackager处理packet
        chunks = self.repackager.add_packet(packet_info)
        
        # 将生成的chunks放入播放队列
        for chunk in chunks:
            self._add_chunk_to_queue(chunk)
    
    def _add_chunk_to_queue(self, chunk: OpusChunk) -> None:
        """将chunk添加到播放队列"""
        try:
            # 检查队列是否过载
            if self.playback_queue.qsize() >= self.max_buffer_chunks:
                print(f"⚠️  播放队列过载，丢弃最旧的chunk")
                try:
                    self.playback_queue.get_nowait()
                except queue.Empty:
                    pass
            
            # 添加新chunk到队列
            self.playback_queue.put(chunk, block=False)
            
            print(f"✓ 添加chunk到播放队列: {chunk.duration_ms:.1f}ms, "
                  f"{chunk.size_bytes}字节, "
                  f"队列大小={self.playback_queue.qsize()}")
            
        except queue.Full:
            print("⚠️  播放队列已满，丢弃chunk")
        except Exception as e:
            print(f"❌ 添加chunk到队列失败: {e}")
    
    def start_playback(self) -> None:
        """启动播放线程"""
        if self.is_running:
            return
        
        self.is_running = True
        self.is_paused = False
        self.playback_thread = threading.Thread(target=self._playback_loop, daemon=True)
        self.playback_thread.start()
        print("▶️  播放线程已启动")
    
    def stop_playback(self) -> None:
        """停止播放"""
        self.is_running = False
        self.is_paused = False
        if self.playback_thread:
            self.playback_thread.join(timeout=1.0)
        print("⏹️  播放线程已停止")
    
    def pause_playback(self) -> None:
        """暂停播放"""
        self.is_paused = True
        print("⏸️  播放已暂停")
    
    def resume_playback(self) -> None:
        """恢复播放"""
        self.is_paused = False
        print("▶️  播放已恢复")
    
    def _playback_loop(self) -> None:
        """播放循环(在独立线程中运行)"""
        while self.is_running:
            try:
                # 如果暂停，等待
                if self.is_paused:
                    time.sleep(0.01)
                    continue
                
                # 从队列获取chunk
                chunk = self.playback_queue.get(timeout=0.1)
                
                # 播放chunk
                self._play_chunk(chunk)
                
                # 更新统计
                self.total_chunks_played += 1
                self.total_duration_played += chunk.duration_ms
                
            except queue.Empty:
                continue
            except Exception as e:
                print(f"❌ 播放错误: {e}")
    
    def _play_chunk(self, chunk: OpusChunk) -> None:
        """播放单个chunk"""
        try:
            # 调用回调函数
            if self.audio_callback:
                self.audio_callback(
                    chunk.pcm_data, 
                    chunk.sample_rate, 
                    chunk.channels
                )
            else:
                # 默认：模拟播放延迟
                time.sleep(chunk.duration_ms / 1000)
                print(f"🔊 播放chunk: {chunk.duration_ms:.1f}ms, "
                      f"{chunk.size_bytes}字节, "
                      f"来自{chunk.original_packet_count}个packet")
            
        except Exception as e:
            print(f"❌ 播放chunk失败: {e}")
    
    def finalize(self) -> None:
        """完成处理，处理剩余的packets"""
        print("🔄 完成处理，处理剩余packets")
        final_chunks = self.repackager.finalize()
        
        # 将剩余的chunks添加到播放队列
        for chunk in final_chunks:
            self._add_chunk_to_queue(chunk)
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        repackager_stats = self.repackager.get_stats()
        return {
            'packets_received': self.total_packets_received,
            'chunks_played': self.total_chunks_played,
            'total_duration_played_ms': self.total_duration_played,
            'playback_queue_size': self.playback_queue.qsize(),
            'is_running': self.is_running,
            'is_paused': self.is_paused,
            'repackager_stats': repackager_stats
        }
    
    def reset(self) -> None:
        """重置播放器状态"""
        # 停止播放
        self.stop_playback()
        
        # 清空播放队列
        while not self.playback_queue.empty():
            try:
                self.playback_queue.get_nowait()
            except queue.Empty:
                break
        
        # 重置repackager
        self.repackager.reset()
        
        # 重置统计
        self.total_packets_received = 0
        self.total_chunks_played = 0
        self.total_duration_played = 0.0
        
        print("🔄 播放器已重置")


# 使用示例
if __name__ == "__main__":
    from opus_stream_parse import OpusStreamParser
    
    # 自定义音频回调
    def my_audio_callback(pcm_data, sample_rate, channels):
        """实际的音频播放逻辑"""
        # 示例：使用pyaudio播放
        # stream.write(pcm_data)
        print(f"🎵 收到音频: {len(pcm_data)}字节, {sample_rate}Hz, {channels}ch")
    
    # 创建解析器和播放器
    parser = OpusStreamParser()
    player = OpusStreamPlayer(
        sample_rate=16000,
        channels=1,
        target_chunk_ms=60.0,  # 每60ms发送一次
        max_buffer_chunks=8,   # 最大缓冲8个chunks
        audio_callback=my_audio_callback
    )
    
    # 启动播放
    player.start_playback()
    
    # 模拟流式数据输入
    with open('your_opus_stream.opus', 'rb') as f:
        while True:
            chunk = f.read(4096)
            if not chunk:
                break
            
            # 解析Ogg Opus流
            results = parser.process_chunk(chunk)
            
            for result in results:
                if result['type'] == 'header':
                    print(f"📋 音频参数: {result['data']['channels']}ch @ {result['data']['sample_rate']}Hz")
                
                elif result['type'] == 'audio':
                    # 添加所有packets
                    for packet in result['packets']:
                        player.add_packet(packet)
                
                elif result['type'] == 'eos':
                    print("🏁 流结束")
                    player.finalize()  # 处理剩余数据
    
    # 等待播放完成
    time.sleep(1)
    
    # 显示统计
    stats = player.get_stats()
    print(f"\n📊 播放器统计:")
    print(f"  接收packets: {stats['packets_received']}")
    print(f"  播放chunks: {stats['chunks_played']}")
    print(f"  总时长: {stats['total_duration_played_ms']:.1f}ms")
    print(f"  队列大小: {stats['playback_queue_size']}")
    print(f"  运行状态: {stats['is_running']}")
    
    # 显示repackager统计
    repackager_stats = stats['repackager_stats']
    print(f"\n📊 Repackager统计:")
    print(f"  输入packets: {repackager_stats['input_packets']}")
    print(f"  输出chunks: {repackager_stats['output_chunks']}")
    print(f"  处理时长: {repackager_stats['duration_processed_ms']:.1f}ms")
    print(f"  平均chunk时长: {repackager_stats['average_chunk_ms']:.1f}ms")
    
    # 停止
    player.stop_playback()