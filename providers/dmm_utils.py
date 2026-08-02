import re


_STANDARD_CODE = re.compile(
    r'^(?P<prefix>[A-Z0-9]*[A-Z])[-_](?P<number>\d{1,8})(?P<suffix>[A-Z]?)$',
    re.IGNORECASE,
)


def normalize_standard_code(value):
    match = _STANDARD_CODE.fullmatch(str(value or '').strip())
    if not match:
        return None
    return {
        'display': (
            f'{match.group("prefix").upper()}-'
            f'{match.group("number")}{match.group("suffix").upper()}'
        ),
        'prefix': match.group('prefix').lower(),
        'number': int(match.group('number')),
        'suffix': match.group('suffix').lower(),
        'compact': (
            f'{match.group("prefix").lower()}'
            f'{match.group("number")}{match.group("suffix").lower()}'
        ),
    }


def dmm_identity_matches(query, *returned_ids):
    """Match a display code against DMM content IDs without fuzzy numbers.

    DMM may add a numeric catalog prefix, zero-pad the number, and append an
    ``r`` rental suffix.  It must not turn FD-153 into MIFD-153 or SMT-030
    into SMT-003.
    """
    expected = normalize_standard_code(query)
    if not expected:
        return False

    for returned_id in returned_ids:
        returned_standard = normalize_standard_code(returned_id)
        if returned_standard:
            same_number = returned_standard['number'] == expected['number']
            same_suffix = returned_standard['suffix'] == expected['suffix']
            same_prefix = returned_standard['prefix'] == expected['prefix']
            # Some filenames contain DMM's three-or-more digit catalog prefix
            # (for example 348NTR-088) while LibreDMM returns the public code
            # NTR-088.  Only strip a leading numeric catalog id; never accept
            # fuzzy letter containment such as MIFD-153 for FD-153.
            catalog_prefixed_query = bool(re.fullmatch(
                rf'\d{{2,5}}{re.escape(returned_standard["prefix"])}',
                expected['prefix'],
            ))
            if same_number and same_suffix and (same_prefix or catalog_prefixed_query):
                return True

        compact = re.sub(r'[^a-z0-9]', '', str(returned_id or '').lower())
        if not compact:
            continue

        expected_compact = re.sub(r'[^a-z0-9]', '', expected['display'].lower())
        if compact == expected_compact:
            return True

        start = 0
        while True:
            index = compact.find(expected['prefix'], start)
            if index < 0:
                break
            numeric_catalog_prefix = compact[:index]
            # DMM content ids also use service/catalog wrappers such as
            # h_066FAD... and td041SERO....  A wrapper must end in at least
            # two digits, which keeps MIFD from ever being treated as FD.
            valid_catalog_prefix = (
                not numeric_catalog_prefix
                or numeric_catalog_prefix.isdigit()
                or bool(re.fullmatch(r'[a-z]{1,6}\d{2,6}', numeric_catalog_prefix))
            )
            if not valid_catalog_prefix:
                start = index + 1
                continue
            remainder = compact[index + len(expected['prefix']):]
            returned_match = re.fullmatch(r'(\d+)([a-z]*)', remainder)
            if returned_match:
                returned_number = int(returned_match.group(1))
                returned_suffix = returned_match.group(2)
                allowed_suffixes = (
                    {'', 'r'}
                    if not expected['suffix']
                    else {expected['suffix'], f'{expected["suffix"]}r'}
                )
                suffix_matches = returned_suffix in allowed_suffixes
                if returned_number == expected['number'] and suffix_matches:
                    return True
            start = index + 1
    return False


def title_with_code(query, title):
    expected = normalize_standard_code(query)
    cleaned_title = ' '.join(str(title or '').split())
    if not expected:
        return cleaned_title
    title_compact = re.sub(r'[^a-z0-9]', '', cleaned_title.lower())
    expected_compact = re.sub(r'[^a-z0-9]', '', expected['display'].lower())
    if expected_compact and expected_compact in title_compact:
        return cleaned_title
    if cleaned_title:
        return f'{expected["display"]} {cleaned_title}'
    return expected['display']


def full_cover_url(value):
    url = str(value or '').strip()
    lowered = url.lower()
    if not url or not lowered.startswith(('http://', 'https://')):
        return ''
    if any(marker in lowered for marker in ('logo', 'placeholder', 'sprite', 'thumb')):
        return ''
    if re.search(r'(?:ps|thumb)\.(?:jpe?g|png|webp)(?:$|\?)', lowered):
        return ''
    if lowered.startswith('http://'):
        return 'https://' + url[len('http://'):]
    return url
