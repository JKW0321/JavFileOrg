"""
原子操作处理器模块 - v1.1-Enhanced 适配版
确保图片下载和文件移动的原子性，支持回滚
适配 v1.1-Enhanced 的批量下载和序列文件处理
"""

import os
import shutil
import tempfile
import errno
import hashlib
import json
import threading
from pathlib import Path
from typing import Tuple, Optional, Dict, Any, List
from PIL import Image


class AtomicOperationCancelled(RuntimeError):
    """Raised when a stop request arrives before a transaction commit boundary."""


class AtomicProcessor:
    """原子操作处理器类 - v1.1-Enhanced 适配版"""
    
    def __init__(self, download_func, sanitize_func, stop_requested=None):
        """
        初始化原子操作处理器
        
        Args:
            download_func: 图片下载函数
            sanitize_func: 文件名清理函数
        """
        self.download_image = download_func
        self.sanitize_filename = sanitize_func
        self.stop_requested = stop_requested or (lambda: False)
        self.temp_dir = Path(tempfile.mkdtemp(prefix="jav_file_organizer_", dir=tempfile.gettempdir()))
        self._transaction_lock = threading.Lock()
        self._active_transactions = 0

    def _begin_transaction(self) -> None:
        with self._transaction_lock:
            self._active_transactions += 1

    def _end_transaction(self) -> None:
        with self._transaction_lock:
            self._active_transactions = max(0, self._active_transactions - 1)

    def has_active_transaction(self) -> bool:
        """Return True while a commit/rollback window could affect source files."""
        with self._transaction_lock:
            return self._active_transactions > 0

    def _raise_if_stopped(self, stage: str = '') -> None:
        if self.stop_requested():
            suffix = f': {stage}' if stage else ''
            raise AtomicOperationCancelled(f'用户取消{suffix}')
    
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
    
    def download_image_to_temp(self, image_source, filename: str) -> Tuple[bool, Optional[Path], str]:
        """
        下载图片到临时目录
        
        Args:
            image_source: 图片URL或包含 referer/fallback_images 的图片任务
            filename: 文件名（含扩展名）
            
        Returns:
            (是否成功, 临时文件路径, 错误信息)
        """
        try:
            self._raise_if_stopped('下载图片前')
            # 清理文件名
            sanitized_name = self.sanitize_filename(filename)
            
            # 生成临时文件路径
            temp_image_path = self.temp_dir / sanitized_name
            
            # 下载图片
            success = self.download_image(image_source, str(temp_image_path))
            
            if not success:
                self._raise_if_stopped('图片下载中')
                return False, None, "图片下载失败"

            self._raise_if_stopped('图片下载后，提交文件前')
            
            # 验证图片完整性
            if not self.validate_image(temp_image_path):
                # 删除无效图片
                if temp_image_path.exists():
                    temp_image_path.unlink()
                return False, None, "图片下载不完整或已损坏"
            
            return True, temp_image_path, "图片下载成功"
            
        except AtomicOperationCancelled:
            if 'temp_image_path' in locals() and temp_image_path.exists():
                try:
                    temp_image_path.unlink()
                except Exception:
                    pass
            raise
        except Exception as e:
            return False, None, f"下载图片到临时目录失败: {e}"

    def _move_temp_image_to_final(self, temp_image_path: Path, final_image_path: str) -> str:
        """将临时图片移动到最终路径，返回最终路径。"""
        shutil.move(str(temp_image_path), final_image_path)
        if not self.validate_image(Path(final_image_path)):
            raise RuntimeError('最终图片校验失败')
        return final_image_path

    def _remove_final_image(self, final_image_path: Optional[str]) -> bool:
        if not final_image_path or not os.path.exists(final_image_path):
            return True
        try:
            os.remove(final_image_path)
            self._fsync_parent_dir(final_image_path)
            return True
        except Exception:
            return False

    def _fsync_file(self, path: str) -> None:
        """Force file content and metadata to disk before reporting success."""
        fd = os.open(path, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    def _fsync_parent_dir(self, path: str) -> None:
        """Force the parent directory entry update to disk."""
        parent = os.path.dirname(os.path.abspath(path)) or '.'
        fd = os.open(parent, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    def _fsync_committed_path(self, path: str) -> None:
        self._fsync_file(path)
        self._fsync_parent_dir(path)

    def _transaction_dir_for_target(self, target_path: str) -> Path:
        return Path(os.path.dirname(os.path.abspath(target_path)) or '.') / '.jfo_transactions'

    def _transaction_journal_path(self, source_path: str, target_path: str) -> Path:
        key = f'{os.path.abspath(source_path)}\0{os.path.abspath(target_path)}'
        digest = hashlib.sha256(key.encode('utf-8')).hexdigest()[:24]
        return self._transaction_dir_for_target(target_path) / f'{digest}.json'

    def _operation_journal_path(self, source_path: str, target_path: str) -> Path:
        key = f'operation\0{os.path.abspath(source_path)}\0{os.path.abspath(target_path)}'
        digest = hashlib.sha256(key.encode('utf-8')).hexdigest()[:24]
        return self._transaction_dir_for_target(target_path) / f'op_{digest}.json'

    def _write_transaction_journal(self, journal_path: Path, payload: Dict[str, Any]) -> None:
        journal_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = journal_path.with_suffix('.json.tmp')
        with open(temp_path, 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_path, journal_path)
        self._fsync_parent_dir(str(journal_path))

    def _remove_transaction_journal(self, journal_path: Path) -> None:
        if journal_path.exists():
            journal_path.unlink()
            self._fsync_parent_dir(str(journal_path))
        try:
            if journal_path.parent.exists() and not any(journal_path.parent.iterdir()):
                journal_path.parent.rmdir()
                self._fsync_parent_dir(str(journal_path.parent))
        except Exception:
            pass

    def _same_size(self, left: str, right: str, expected_size: Optional[int] = None) -> bool:
        if not (os.path.exists(left) and os.path.exists(right)):
            return False
        left_size = os.path.getsize(left)
        right_size = os.path.getsize(right)
        if expected_size is not None and left_size != expected_size:
            return False
        return left_size == right_size

    def _recover_operation_transaction(self, journal_path: Path, payload: Dict[str, Any]) -> str:
        temp_image_path = payload.get('temp_image_path')
        final_image_path = payload.get('final_image_path')
        unresolved = []
        if final_image_path:
            if not self._remove_final_image(final_image_path):
                unresolved.append(f'image-remove-failed:{os.path.basename(final_image_path)}')
        if temp_image_path and os.path.exists(temp_image_path):
            try:
                os.remove(temp_image_path)
            except OSError as exc:
                unresolved.append(f'temp-image-remove-failed:{exc}')

        rolled_back = 0
        sources = payload.get('sources') or []
        for item in reversed(sources):
            source_path = item.get('source_path')
            target_path = item.get('target_path')
            expected_size = item.get('source_size')
            expected_size = int(expected_size) if expected_size is not None else None
            if not source_path or not target_path:
                unresolved.append('missing-path')
                continue

            source_exists = os.path.exists(source_path)
            target_exists = os.path.exists(target_path)
            if target_exists and not source_exists:
                if expected_size is not None and os.path.getsize(target_path) != expected_size:
                    unresolved.append(f'size-mismatch:{os.path.basename(target_path)}')
                    continue
                self._move_video(target_path, source_path)
                self._fsync_committed_path(source_path)
                self._fsync_parent_dir(target_path)
                rolled_back += 1
            elif target_exists and source_exists:
                if self._same_size(source_path, target_path, expected_size):
                    os.remove(target_path)
                    self._fsync_parent_dir(target_path)
                    rolled_back += 1
                else:
                    unresolved.append(f'duplicate-size-mismatch:{os.path.basename(target_path)}')
            elif not target_exists and source_exists:
                continue
            else:
                unresolved.append(f'missing-source-and-target:{os.path.basename(source_path)}')

        if unresolved:
            return f'unresolved-operation:{",".join(unresolved)}'
        self._remove_transaction_journal(journal_path)
        return f'rolled-back-operation:{rolled_back}'

    def _recover_transaction(self, journal_path: Path) -> str:
        with open(journal_path, 'r', encoding='utf-8') as f:
            payload = json.load(f)
        if payload.get('kind') == 'file-operation':
            return self._recover_operation_transaction(journal_path, payload)
        source_path = payload.get('source_path')
        target_path = payload.get('target_path')
        temp_path = payload.get('temp_path')
        expected_size = payload.get('source_size')
        expected_size = int(expected_size) if expected_size is not None else None

        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)
            self._fsync_parent_dir(temp_path)

        source_exists = bool(source_path and os.path.exists(source_path))
        target_exists = bool(target_path and os.path.exists(target_path))

        if source_exists and target_exists:
            if self._same_size(source_path, target_path, expected_size):
                os.remove(target_path)
                self._fsync_parent_dir(target_path)
                self._remove_transaction_journal(journal_path)
                return 'rolled-back-duplicate-target'
            return 'unresolved-size-mismatch'

        if source_exists and not target_exists:
            self._remove_transaction_journal(journal_path)
            return 'source-preserved'

        if target_exists and not source_exists:
            self._remove_transaction_journal(journal_path)
            return 'target-already-committed'

        self._remove_transaction_journal(journal_path)
        return 'nothing-left'

    def recover_pending_transactions(self, finish_folder: str) -> List[str]:
        journal_dir = Path(finish_folder) / '.jfo_transactions'
        if not journal_dir.exists():
            return []
        actions = []
        for journal_path in sorted(journal_dir.glob('*.json')):
            try:
                actions.append(self._recover_transaction(journal_path))
            except Exception as exc:
                actions.append(f'recovery-failed:{journal_path.name}:{exc}')
        return actions

    def _rename_video(self, source_path: str, target_path: str) -> None:
        os.rename(source_path, target_path)

    def _copy_across_filesystems(self, source_path: str, target_path: str) -> None:
        """Copy through a temp file in the target directory, then commit by rename."""
        target_dir = os.path.dirname(os.path.abspath(target_path)) or '.'
        target_name = os.path.basename(target_path)
        journal_path = self._transaction_journal_path(source_path, target_path)
        source_size = os.path.getsize(source_path)
        temp_path = None
        try:
            self._write_transaction_journal(journal_path, {
                'status': 'copying',
                'source_path': source_path,
                'target_path': target_path,
                'temp_path': None,
                'source_size': source_size,
            })
            fd, temp_path = tempfile.mkstemp(
                prefix=f'.{target_name}.',
                suffix='.jfo-tmp',
                dir=target_dir,
            )
            os.close(fd)
            self._write_transaction_journal(journal_path, {
                'status': 'copying',
                'source_path': source_path,
                'target_path': target_path,
                'temp_path': temp_path,
                'source_size': source_size,
            })
            shutil.copy2(source_path, temp_path)
            if os.path.getsize(temp_path) != source_size:
                raise RuntimeError('跨文件系统复制大小校验失败')
            self._fsync_committed_path(temp_path)
            os.rename(temp_path, target_path)
            temp_path = None
            self._fsync_parent_dir(target_path)
            self._write_transaction_journal(journal_path, {
                'status': 'target-committed',
                'source_path': source_path,
                'target_path': target_path,
                'temp_path': None,
                'source_size': source_size,
            })
            os.unlink(source_path)
            self._fsync_parent_dir(source_path)
            self._remove_transaction_journal(journal_path)
        except Exception:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                    self._fsync_parent_dir(temp_path)
                except Exception:
                    pass
            raise

    def _move_video(self, source_path: str, target_path: str) -> None:
        """移动视频文件；跨文件系统时用目标目录临时文件提交，避免半成品目标文件。"""
        try:
            self._rename_video(source_path, target_path)
        except OSError as exc:
            if exc.errno != errno.EXDEV:
                raise
            self._copy_across_filesystems(source_path, target_path)

    def _rollback_video(self, target_path: str, original_path: str) -> bool:
        """尽量把已移动的视频放回源路径。"""
        if not target_path or not os.path.exists(target_path):
            return True
        try:
            journal_path = self._transaction_journal_path(original_path, target_path)
            if os.path.exists(original_path):
                if os.path.getsize(original_path) == os.path.getsize(target_path):
                    os.remove(target_path)
                    self._fsync_parent_dir(target_path)
                    self._fsync_committed_path(original_path)
                    self._remove_transaction_journal(journal_path)
                    return True
                return False
            self._move_video(target_path, original_path)
            self._fsync_committed_path(original_path)
            self._fsync_parent_dir(target_path)
            self._remove_transaction_journal(journal_path)
            return True
        except Exception:
            return False

    def _empty_file_result(self, *, status: str = 'failed', reason: str = '',
                           rollback_ok: Optional[bool] = None) -> Dict[str, Any]:
        return {
            'status': status,
            'reason': reason,
            'rollback_ok': rollback_ok,
            'video_moved': False,
            'image_downloaded': False,
            'video_path': None,
            'image_path': None,
        }
    
    def process_file_atomic(self, file_path: str, new_filename: str, image_source,
                           finish_folder: str) -> Tuple[bool, Dict[str, Any], str]:
        """
        原子性处理文件：先下载图片，验证成功后再移动文件
        
        Args:
            file_path: 原始文件路径
            new_filename: 新文件名（含扩展名）
            image_source: 图片URL或包含 referer/fallback_images 的图片任务（可选）
            finish_folder: 目标文件夹
            
        Returns:
            (是否成功, 结果信息字典, 消息)
        """
        temp_image_path = None
        new_video_path = None
        final_image_path = None
        rollback_ok = None
        transaction_started = False
        operation_journal_path = None
        
        try:
            self._raise_if_stopped('单文件事务开始前')
            if not image_source:
                message = "缺少图片URL，严格事务模式下不移动源视频"
                return False, self._empty_file_result(reason=message), message

            self.recover_pending_transactions(finish_folder)
            source_size = os.path.getsize(file_path)
            # 步骤1: 如果有图片URL，先下载到临时目录
            video_basename = os.path.splitext(new_filename)[0]
            image_filename = f"{video_basename}.jpg"
            
            success, temp_image_path, message = self.download_image_to_temp(image_source, image_filename)
            if not success:
                reason = f"图片下载失败: {message}"
                return False, self._empty_file_result(reason=reason), reason
            self._raise_if_stopped('视频移动前')
            self._begin_transaction()
            transaction_started = True
            
            # 步骤2: 移动视频文件
            new_video_path = os.path.join(finish_folder, new_filename)
            
            # 处理重名文件
            counter = 1
            base_new_path = new_video_path
            while os.path.exists(new_video_path):
                name, ext = os.path.splitext(base_new_path)
                new_video_path = f"{name}_{counter}{ext}"
                counter += 1

            video_basename = os.path.splitext(os.path.basename(new_video_path))[0]
            image_filename = f"{video_basename}.jpg"
            final_image_path = os.path.join(finish_folder, image_filename)
            if os.path.exists(final_image_path):
                counter = 1
                base_image_path = final_image_path
                while os.path.exists(final_image_path):
                    name, ext = os.path.splitext(base_image_path)
                    final_image_path = f"{name}_{counter}{ext}"
                    counter += 1

            operation_journal_path = self._operation_journal_path(file_path, new_video_path)
            self._write_transaction_journal(operation_journal_path, {
                'kind': 'file-operation',
                'status': 'committing',
                'sources': [{
                    'source_path': file_path,
                    'target_path': new_video_path,
                    'source_size': source_size,
                }],
                'temp_image_path': str(temp_image_path) if temp_image_path else None,
                'final_image_path': final_image_path,
            })
            
            self._move_video(file_path, new_video_path)
            
            # v1.5.1: 移动后做大小校验，防止占位/异常小文件混入 Finish
            moved_size = os.path.getsize(new_video_path)
            if moved_size != source_size:
                raise RuntimeError(
                    f"视频大小校验失败: source={source_size} bytes, target={moved_size} bytes"
                )
            self._fsync_committed_path(new_video_path)
            self._raise_if_stopped('图片提交前')

            # 步骤3: 如果有临时图片，移动到最终位置
            if temp_image_path and temp_image_path.exists():
                self._move_temp_image_to_final(temp_image_path, final_image_path)
                self._fsync_committed_path(final_image_path)
                if operation_journal_path:
                    self._remove_transaction_journal(operation_journal_path)
                
                return True, {
                    'status': 'success',
                    'reason': '',
                    'rollback_ok': None,
                    'video_moved': True,
                    'video_path': new_video_path,
                    'image_downloaded': True,
                    'image_path': final_image_path
                }, "文件和图片处理成功"
            
            raise RuntimeError("图片临时文件缺失，无法完成严格事务")

        except AtomicOperationCancelled as e:
            if new_video_path and os.path.exists(new_video_path):
                rollback_ok = self._rollback_video(new_video_path, file_path)
            final_image_removed = self._remove_final_image(final_image_path)
            if temp_image_path and temp_image_path.exists():
                try:
                    temp_image_path.unlink()
                except Exception:
                    pass
            if operation_journal_path and rollback_ok is not False and final_image_removed:
                self._remove_transaction_journal(operation_journal_path)
            return False, {
                'status': 'cancelled',
                'reason': str(e),
                'rollback_ok': rollback_ok,
                'video_moved': False,
                'image_downloaded': False,
                'video_path': None,
                'image_path': None
            }, str(e)
            
        except Exception as e:
            # 尝试回滚视频文件移动
            if new_video_path and os.path.exists(new_video_path):
                rollback_ok = self._rollback_video(new_video_path, file_path)
            final_image_removed = self._remove_final_image(final_image_path)
            
            # 清理临时图片
            if temp_image_path and temp_image_path.exists():
                try:
                    temp_image_path.unlink()
                except:
                    pass
            if operation_journal_path and rollback_ok is not False and final_image_removed:
                self._remove_transaction_journal(operation_journal_path)
            
            return False, {
                'status': 'failed' if rollback_ok is not False else 'critical',
                'reason': f"原子操作失败: {e}",
                'rollback_ok': rollback_ok,
                'video_moved': False,
                'image_downloaded': False,
                'video_path': None,
                'image_path': None
            }, f"原子操作失败: {e}"
        finally:
            if transaction_started:
                self._end_transaction()

    def process_series_group_atomic(self, series_files, title: str, image_source, finish_folder: str):
        """以事务性方式处理一个序列文件组。

        series_files: [(file_path, sequence), ...]
        成功条件：全部视频正确移动且（如果需要）图片正确落盘；否则尽量回滚源文件。
        """
        temp_image_path = None
        moved_videos = []
        final_image_path = None
        transaction_started = False
        operation_journal_path = None
        try:
            self._raise_if_stopped('序列组事务开始前')
            if not series_files:
                return False, {'video_paths': [], 'image_path': None, 'image_downloaded': False}, '空序列组'
            if not image_source:
                return False, {
                    'status': 'failed',
                    'reason': '缺少图片URL，严格事务模式下不移动源视频',
                    'rollback_ok': None,
                    'video_paths': [],
                    'image_path': None,
                    'image_downloaded': False,
                }, '缺少图片URL，严格事务模式下不移动源视频'

            self.recover_pending_transactions(finish_folder)
            # 1) 先下载图片到临时目录，确保不会先移动视频后图失败
            success, temp_image_path, message = self.download_image_to_temp(image_source, f"{title}.jpg")
            if not success:
                return False, {
                    'status': 'failed',
                    'reason': message,
                    'rollback_ok': None,
                    'video_paths': [],
                    'image_path': None,
                    'image_downloaded': False,
                }, message
            self._raise_if_stopped('序列组视频移动前')

            # 2) 计算每个视频的最终路径（含重名处理）
            planned = []
            reserved_targets = set()
            for file_path, sequence in series_files:
                filename = os.path.basename(file_path)
                file_ext = os.path.splitext(filename)[1]
                source_size = os.path.getsize(file_path)
                new_filename = self.sanitize_filename(f"{title}-{sequence}{file_ext}")
                target_path = os.path.join(finish_folder, new_filename)
                counter = 1
                base_target_path = target_path
                while os.path.exists(target_path) or target_path in reserved_targets:
                    name, ext = os.path.splitext(base_target_path)
                    target_path = f"{name}_{counter}{ext}"
                    counter += 1
                planned.append((file_path, target_path, source_size))
                reserved_targets.add(target_path)

            final_image_path = os.path.join(finish_folder, self.sanitize_filename(f"{title}.jpg"))
            counter = 1
            base_image_path = final_image_path
            while os.path.exists(final_image_path):
                name, ext = os.path.splitext(base_image_path)
                final_image_path = f"{name}_{counter}{ext}"
                counter += 1

            operation_journal_path = self._operation_journal_path(planned[0][0], planned[0][1])
            self._write_transaction_journal(operation_journal_path, {
                'kind': 'file-operation',
                'status': 'committing',
                'sources': [
                    {
                        'source_path': file_path,
                        'target_path': target_path,
                        'source_size': source_size,
                    }
                    for file_path, target_path, source_size in planned
                ],
                'temp_image_path': str(temp_image_path) if temp_image_path else None,
                'final_image_path': final_image_path,
            })

            # 3) 逐个移动并做大小校验；任何一个失败都回滚之前已移动的视频
            self._begin_transaction()
            transaction_started = True
            for file_path, target_path, source_size in planned:
                self._raise_if_stopped('序列组视频移动中')
                self._move_video(file_path, target_path)
                moved_size = os.path.getsize(target_path)
                if moved_size != source_size:
                    raise RuntimeError(
                        f"视频大小校验失败: source={source_size} bytes, target={moved_size} bytes"
                    )
                self._fsync_committed_path(target_path)
                moved_videos.append((file_path, target_path))

            # 4) 全部视频成功后，再提交图片
            self._raise_if_stopped('序列组图片提交前')
            if temp_image_path and temp_image_path.exists():
                self._move_temp_image_to_final(temp_image_path, final_image_path)
                self._fsync_committed_path(final_image_path)
                if operation_journal_path:
                    self._remove_transaction_journal(operation_journal_path)

            return True, {
                'status': 'success',
                'reason': '',
                'rollback_ok': None,
                'video_paths': [target for _, target in moved_videos],
                'image_path': final_image_path,
                'image_downloaded': bool(final_image_path),
            }, '序列文件组处理成功'

        except AtomicOperationCancelled as e:
            rollback_ok = True
            for original_path, target_path in reversed(moved_videos):
                if not self._rollback_video(target_path, original_path):
                    rollback_ok = False
            final_image_removed = self._remove_final_image(final_image_path)
            if temp_image_path and temp_image_path.exists():
                try:
                    temp_image_path.unlink()
                except Exception:
                    pass
            if operation_journal_path and rollback_ok and final_image_removed:
                self._remove_transaction_journal(operation_journal_path)
            return False, {
                'status': 'cancelled',
                'reason': str(e),
                'rollback_ok': rollback_ok,
                'video_paths': [],
                'image_path': None,
                'image_downloaded': False,
            }, str(e)

        except Exception as e:
            # 回滚已经移动的视频
            rollback_ok = True
            for original_path, target_path in reversed(moved_videos):
                if not self._rollback_video(target_path, original_path):
                    rollback_ok = False
            # 删除最终图片（如果已写出）
            final_image_removed = self._remove_final_image(final_image_path)
            # 清理临时图片
            if temp_image_path and temp_image_path.exists():
                try:
                    temp_image_path.unlink()
                except Exception:
                    pass
            if operation_journal_path and rollback_ok and final_image_removed:
                self._remove_transaction_journal(operation_journal_path)
            return False, {
                'status': 'failed' if rollback_ok else 'critical',
                'reason': f"序列文件组原子处理失败: {e}",
                'rollback_ok': rollback_ok,
                'video_paths': [],
                'image_path': None,
                'image_downloaded': False,
            }, f"序列文件组原子处理失败: {e}"
        finally:
            if transaction_started:
                self._end_transaction()
    
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
                try:
                    self.temp_dir.rmdir()
                except OSError:
                    pass
        except Exception as e:
            print(f"清理临时目录失败: {e}")
    
    def __del__(self):
        """析构函数，清理临时文件"""
        try:
            self.cleanup_temp_files()
        except:
            pass
