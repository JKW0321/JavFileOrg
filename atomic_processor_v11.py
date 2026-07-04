"""
原子操作处理器模块 - v1.1-Enhanced 适配版
确保图片下载和文件移动的原子性，支持回滚
适配 v1.1-Enhanced 的批量下载和序列文件处理
"""

import os
import shutil
import tempfile
from pathlib import Path
from typing import Tuple, Optional, Dict, Any, List
from PIL import Image


class AtomicProcessor:
    """原子操作处理器类 - v1.1-Enhanced 适配版"""
    
    def __init__(self, download_func, sanitize_func):
        """
        初始化原子操作处理器
        
        Args:
            download_func: 图片下载函数
            sanitize_func: 文件名清理函数
        """
        self.download_image = download_func
        self.sanitize_filename = sanitize_func
        self.temp_dir = Path(tempfile.gettempdir()) / "jav_file_organizer_temp"
        self.temp_dir.mkdir(parents=True, exist_ok=True)
    
    def validate_image(self, image_path: Path) -> bool:
        """
        验证图片文件是否完整有效 - 优化版：只打开一次
        
        Args:
            image_path: 图片文件路径
            
        Returns:
            是否有效
        """
        try:
            # 检查文件是否存在且大小大于0
            if not image_path.exists() or image_path.stat().st_size == 0:
                return False
            
            # 优化：只打开一次，同时验证和加载
            with Image.open(image_path) as img:
                img.load()  # 加载图片数据，如果损坏会抛出异常
                # 检查基本属性
                _ = img.size  # 确认可以读取尺寸
                _ = img.mode  # 确认可以读取模式
            
            return True
            
        except Exception as e:
            print(f"图片验证失败: {e}")
            return False
    
    def download_image_to_temp(self, image_url: str, filename: str) -> Tuple[bool, Optional[Path], str]:
        """
        下载图片到临时目录
        
        Args:
            image_url: 图片URL
            filename: 文件名（含扩展名）
            
        Returns:
            (是否成功, 临时文件路径, 错误信息)
        """
        try:
            # 清理文件名
            sanitized_name = self.sanitize_filename(filename)
            
            # 生成临时文件路径
            temp_image_path = self.temp_dir / sanitized_name
            
            # 下载图片
            success = self.download_image(image_url, str(temp_image_path))
            
            if not success:
                return False, None, "图片下载失败"
            
            # 验证图片完整性
            if not self.validate_image(temp_image_path):
                # 删除无效图片
                if temp_image_path.exists():
                    temp_image_path.unlink()
                return False, None, "图片下载不完整或已损坏"
            
            return True, temp_image_path, "图片下载成功"
            
        except Exception as e:
            return False, None, f"下载图片到临时目录失败: {e}"

    def _move_temp_image_to_final(self, temp_image_path: Path, final_image_path: str) -> str:
        """将临时图片移动到最终路径，返回最终路径。"""
        shutil.move(str(temp_image_path), final_image_path)
        return final_image_path
    
    def process_file_atomic(self, file_path: str, new_filename: str, image_url: Optional[str], 
                           finish_folder: str) -> Tuple[bool, Dict[str, Any], str]:
        """
        原子性处理文件：先下载图片，验证成功后再移动文件
        
        Args:
            file_path: 原始文件路径
            new_filename: 新文件名（含扩展名）
            image_url: 图片URL（可选）
            finish_folder: 目标文件夹
            
        Returns:
            (是否成功, 结果信息字典, 消息)
        """
        temp_image_path = None
        new_video_path = None
        final_image_path = None
        
        try:
            source_size = os.path.getsize(file_path)
            # 步骤1: 如果有图片URL，先下载到临时目录
            if image_url:
                # 生成图片文件名
                video_basename = os.path.splitext(new_filename)[0]
                image_filename = f"{video_basename}.jpg"
                
                success, temp_image_path, message = self.download_image_to_temp(image_url, image_filename)
                if not success:
                    return False, {
                        'video_moved': False,
                        'image_downloaded': False,
                        'video_path': None,
                        'image_path': None
                    }, f"图片下载失败: {message}"
            
            # 步骤2: 移动视频文件
            new_video_path = os.path.join(finish_folder, new_filename)
            
            # 处理重名文件
            counter = 1
            base_new_path = new_video_path
            while os.path.exists(new_video_path):
                name, ext = os.path.splitext(base_new_path)
                new_video_path = f"{name}_{counter}{ext}"
                counter += 1
            
            # 优先使用 os.rename (同文件系统下极快)
            try:
                os.rename(file_path, new_video_path)
            except OSError:
                # 跨文件系统时使用 shutil.move
                shutil.move(file_path, new_video_path)
            
            # v1.5.1: 移动后做大小校验，防止占位/异常小文件混入 Finish
            moved_size = os.path.getsize(new_video_path)
            if moved_size != source_size:
                raise RuntimeError(
                    f"视频大小校验失败: source={source_size} bytes, target={moved_size} bytes"
                )

            # 步骤3: 如果有临时图片，移动到最终位置
            if temp_image_path and temp_image_path.exists():
                try:
                    # 构建最终图片路径（使用实际的视频文件名）
                    video_basename = os.path.splitext(os.path.basename(new_video_path))[0]
                    image_filename = f"{video_basename}.jpg"
                    final_image_path = os.path.join(finish_folder, image_filename)
                    
                    # 检查图片同名冲突
                    if os.path.exists(final_image_path):
                        counter = 1
                        base_image_path = final_image_path
                        while os.path.exists(final_image_path):
                            name, ext = os.path.splitext(base_image_path)
                            final_image_path = f"{name}_{counter}{ext}"
                            counter += 1
                    
                    # 移动图片到最终位置
                    shutil.move(str(temp_image_path), final_image_path)
                    
                    return True, {
                        'video_moved': True,
                        'video_path': new_video_path,
                        'image_downloaded': True,
                        'image_path': final_image_path
                    }, "文件和图片处理成功"
                    
                except Exception as e:
                    # 图片移动失败，但视频已经成功移动
                    # 清理临时图片
                    if temp_image_path and temp_image_path.exists():
                        temp_image_path.unlink()
                    
                    return True, {
                        'video_moved': True,
                        'video_path': new_video_path,
                        'image_downloaded': False,
                        'image_path': None
                    }, f"视频处理成功，但图片移动失败: {e}"
            
            # 没有图片URL的情况
            return True, {
                'video_moved': True,
                'video_path': new_video_path,
                'image_downloaded': False,
                'image_path': None
            }, "文件处理成功（无图片）"
            
        except Exception as e:
            # 尝试回滚视频文件移动
            if new_video_path and os.path.exists(new_video_path):
                try:
                    os.rename(new_video_path, file_path)
                except:
                    pass
            
            # 清理临时图片
            if temp_image_path and temp_image_path.exists():
                try:
                    temp_image_path.unlink()
                except:
                    pass
            
            return False, {
                'video_moved': False,
                'image_downloaded': False,
                'video_path': None,
                'image_path': None
            }, f"原子操作失败: {e}"

    def process_series_group_atomic(self, series_files, title: str, image_url: Optional[str], finish_folder: str):
        """以事务性方式处理一个序列文件组。

        series_files: [(file_path, sequence), ...]
        成功条件：全部视频正确移动且（如果需要）图片正确落盘；否则尽量回滚源文件。
        """
        temp_image_path = None
        moved_videos = []
        final_image_path = None
        try:
            if not series_files:
                return False, {'video_paths': [], 'image_path': None, 'image_downloaded': False}, '空序列组'

            # 1) 先下载图片到临时目录，确保不会先移动视频后图失败
            if image_url:
                success, temp_image_path, message = self.download_image_to_temp(image_url, f"{title}.jpg")
                if not success:
                    return False, {'video_paths': [], 'image_path': None, 'image_downloaded': False}, message

            # 2) 计算每个视频的最终路径（含重名处理）
            planned = []
            for file_path, sequence in series_files:
                filename = os.path.basename(file_path)
                file_ext = os.path.splitext(filename)[1]
                new_filename = self.sanitize_filename(f"{title}-{sequence}{file_ext}")
                target_path = os.path.join(finish_folder, new_filename)
                counter = 1
                base_target_path = target_path
                while os.path.exists(target_path):
                    name, ext = os.path.splitext(base_target_path)
                    target_path = f"{name}_{counter}{ext}"
                    counter += 1
                planned.append((file_path, target_path))

            # 3) 逐个移动并做大小校验；任何一个失败都回滚之前已移动的视频
            for file_path, target_path in planned:
                source_size = os.path.getsize(file_path)
                try:
                    os.rename(file_path, target_path)
                except OSError:
                    shutil.move(file_path, target_path)
                moved_size = os.path.getsize(target_path)
                if moved_size != source_size:
                    raise RuntimeError(
                        f"视频大小校验失败: source={source_size} bytes, target={moved_size} bytes"
                    )
                moved_videos.append((file_path, target_path))

            # 4) 全部视频成功后，再提交图片
            if temp_image_path and temp_image_path.exists():
                final_image_path = os.path.join(finish_folder, self.sanitize_filename(f"{title}.jpg"))
                counter = 1
                base_image_path = final_image_path
                while os.path.exists(final_image_path):
                    name, ext = os.path.splitext(base_image_path)
                    final_image_path = f"{name}_{counter}{ext}"
                    counter += 1
                self._move_temp_image_to_final(temp_image_path, final_image_path)

            return True, {
                'video_paths': [target for _, target in moved_videos],
                'image_path': final_image_path,
                'image_downloaded': bool(final_image_path),
            }, '序列文件组处理成功'

        except Exception as e:
            # 回滚已经移动的视频
            for original_path, target_path in reversed(moved_videos):
                try:
                    if os.path.exists(target_path):
                        os.rename(target_path, original_path)
                except Exception:
                    pass
            # 删除最终图片（如果已写出）
            if final_image_path and os.path.exists(final_image_path):
                try:
                    os.remove(final_image_path)
                except Exception:
                    pass
            # 清理临时图片
            if temp_image_path and temp_image_path.exists():
                try:
                    temp_image_path.unlink()
                except Exception:
                    pass
            return False, {
                'video_paths': [],
                'image_path': None,
                'image_downloaded': False,
            }, f"序列文件组原子处理失败: {e}"
    
    def cleanup_temp_files(self):
        """清理临时文件"""
        try:
            if self.temp_dir.exists():
                for file in self.temp_dir.iterdir():
                    try:
                        if file.is_file():
                            file.unlink()
                    except Exception as e:
                        print(f"清理临时文件失败 {file}: {e}")
        except Exception as e:
            print(f"清理临时目录失败: {e}")
    
    def __del__(self):
        """析构函数，清理临时文件"""
        try:
            self.cleanup_temp_files()
        except:
            pass
