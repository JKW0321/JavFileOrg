#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Persistence helpers for filename rule-learning observations."""
from __future__ import annotations

import json
import os
from datetime import datetime


def write_filename_rule_candidates(path, candidates):
    """Write deduplicated filename rule candidates to a JSON audit file."""
    os.makedirs(os.path.dirname(path), exist_ok=True)

    deduped = []
    seen = set()
    for candidate in candidates:
        key = (
            candidate.get('rule_id'),
            candidate.get('normalized_code'),
            candidate.get('source_name'),
            candidate.get('sequence'),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)

    payload = {
        'generated_at': datetime.now().isoformat(),
        'counts': {
            'total': len(deduped),
            'auto_usable': sum(1 for item in deduped if item.get('usable_for_search')),
            'needs_review': sum(1 for item in deduped if not item.get('usable_for_search')),
        },
        'candidates': deduped,
    }

    with open(path, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return path
