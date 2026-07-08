#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shared download helpers for image assets."""
from __future__ import annotations

import os
import re
import time
from typing import Callable
from urllib.parse import urlparse


class ImageDownloader:
    """Download images with retry, timeout, stop checks, and partial-file cleanup."""

    def __init__(self, *, session, log: Callable, stop_requested: Callable[[], bool],
                 referer: str = 'https://www.javbus.com/'):
        self.session = session
        self.log = log
        self.stop_requested = stop_requested
        self.referer = referer

    def _headers(self, referer=None, provider=None):
        session_headers = getattr(self.session, 'headers', {}) or {}
        referer = referer or self.referer
        headers = {
            'Referer': referer,
            'User-Agent': session_headers.get('User-Agent', 'Mozilla/5.0'),
            'Accept': 'image/webp,image/apng,image/*,*/*;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
        }
        if referer:
            parsed = urlparse(referer)
            if parsed.scheme and parsed.netloc:
                headers['Origin'] = f'{parsed.scheme}://{parsed.netloc}'
        return headers

    def _remove_partial_file(self, path):
        if not os.path.exists(path):
            return
        try:
            os.remove(path)
        except OSError as exc:
            self.log(f"⚠️ 无法清理不完整图片: {exc}", "WARNING")

    def _image_task(self, image_source):
        if isinstance(image_source, dict):
            primary = image_source.get('image_url') or image_source.get('url')
            fallbacks = image_source.get('fallback_images') or []
            urls = []
            for url in [primary] + list(fallbacks):
                if url and url not in urls:
                    urls.append(url)
            return {
                'urls': urls,
                'referer': image_source.get('referer') or image_source.get('detail_url') or self.referer,
                'provider': image_source.get('provider'),
            }
        return {
            'urls': [image_source] if image_source else [],
            'referer': self.referer,
            'provider': None,
        }

    def _status_code_from_exception(self, exc):
        response = getattr(exc, 'response', None)
        status_code = getattr(response, 'status_code', None)
        if status_code is not None:
            return status_code
        match = re.search(r'\b([45]\d{2})\b', str(exc))
        return int(match.group(1)) if match else None

    def _is_retryable_exception(self, exc):
        status_code = self._status_code_from_exception(exc)
        if status_code is not None:
            if status_code in {408, 409, 425, 429}:
                return True
            if 500 <= status_code <= 599:
                return True
            return False
        text = str(exc).lower()
        non_retryable_markers = ('forbidden', 'not found', '404', '403')
        if any(marker in text for marker in non_retryable_markers):
            return False
        return True

    def _wait_before_retry(self, seconds):
        steps = max(1, int(seconds / 0.25))
        step_seconds = seconds / steps
        for _ in range(steps):
            if self.stop_requested():
                return False
            time.sleep(step_seconds)
            if self.stop_requested():
                return False
        return True

    def download(self, image_url, save_path, max_retries=3):
        task = self._image_task(image_url)
        urls = task['urls']
        if not urls:
            self.log("❌ 图片下载失败: 缺少图片URL", "ERROR")
            return False

        last_error = None
        for url_index, url in enumerate(urls, start=1):
            for attempt in range(max_retries):
                try:
                    if self.stop_requested():
                        return False

                    response = self.session.get(
                        url,
                        headers=self._headers(referer=task.get('referer'), provider=task.get('provider')),
                        timeout=(10, 60),
                        stream=True,
                    )
                    response.raise_for_status()

                    with open(save_path, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=65536):
                            if self.stop_requested():
                                raise RuntimeError("用户中断")
                            if chunk:
                                f.write(chunk)

                    if os.path.exists(save_path) and os.path.getsize(save_path) > 0:
                        self.log(f"✅ 图片下载成功: {os.path.basename(save_path)}", "SUCCESS")
                        return True
                    raise RuntimeError("下载的文件为空")

                except Exception as exc:
                    last_error = exc
                    self._remove_partial_file(save_path)
                    retryable = self._is_retryable_exception(exc)
                    has_retry = retryable and attempt < max_retries - 1
                    if has_retry:
                        wait_time = 2 ** attempt
                        self.log(
                            f"⚠️ 图片下载失败 (候选 {url_index}/{len(urls)}，尝试 {attempt + 1}/{max_retries}): {exc}",
                            "WARNING",
                        )
                        self.log(f"🔄 {wait_time}秒后重试...", "INFO")
                        if not self._wait_before_retry(wait_time):
                            self.log("⚠️ 图片下载重试等待期间收到停止请求", "WARNING")
                            return False
                    else:
                        level = "WARNING" if url_index < len(urls) else "ERROR"
                        self.log(
                            f"{'⚠️' if level == 'WARNING' else '❌'} 图片候选失败 (候选 {url_index}/{len(urls)}): {exc}",
                            level,
                        )
                        break

        self.log(f"❌ 图片下载失败: 所有候选均不可用: {last_error}", "ERROR")
        return False
