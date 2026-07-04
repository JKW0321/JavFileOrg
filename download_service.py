#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shared download helpers for image assets."""
from __future__ import annotations

import os
import time
from typing import Callable


class ImageDownloader:
    """Download images with retry, timeout, stop checks, and partial-file cleanup."""

    def __init__(self, *, session, log: Callable, stop_requested: Callable[[], bool],
                 referer: str = 'https://www.javbus.com/'):
        self.session = session
        self.log = log
        self.stop_requested = stop_requested
        self.referer = referer

    def _headers(self):
        session_headers = getattr(self.session, 'headers', {}) or {}
        return {
            'Referer': self.referer,
            'User-Agent': session_headers.get('User-Agent', 'Mozilla/5.0'),
            'Accept': 'image/webp,image/apng,image/*,*/*;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
        }

    def _remove_partial_file(self, path):
        if not os.path.exists(path):
            return
        try:
            os.remove(path)
        except OSError as exc:
            self.log(f"⚠️ 无法清理不完整图片: {exc}", "WARNING")

    def download(self, image_url, save_path, max_retries=3):
        for attempt in range(max_retries):
            try:
                if self.stop_requested():
                    return False

                response = self.session.get(
                    image_url,
                    headers=self._headers(),
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
                self._remove_partial_file(save_path)
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    self.log(f"⚠️ 图片下载失败 (尝试 {attempt + 1}/{max_retries}): {exc}", "WARNING")
                    self.log(f"🔄 {wait_time}秒后重试...", "INFO")
                    time.sleep(wait_time)
                else:
                    self.log(f"❌ 图片下载失败 (已重试 {max_retries} 次): {exc}", "ERROR")
                    return False

        return False
