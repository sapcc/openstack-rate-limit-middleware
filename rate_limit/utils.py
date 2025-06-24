# NOTE: This function was copied from
# https://github.com/andymccurdy/redis-py/blob/master/redis/utils.py#L29
def str_if_bytes(value):
    return (
        value.decode('utf-8', errors='replace')
        if isinstance(value, bytes)
        else value
    )


# NOTE: This function was copied from
# https://github.com/andymccurdy/redis-py/blob/master/redis/client.py#L114
def parse_info(response):
    """Parse the result of Redis's INFO command into a Python dict."""
    info = {}
    response = str_if_bytes(response)

    def get_value(value):
        if ',' not in value or '=' not in value:
            try:
                if '.' in value:
                    return float(value)
                else:
                    return int(value)
            except ValueError:
                return value
        else:
            sub_dict = {}
            for item in value.split(','):
                k, v = item.rsplit('=', 1)
                sub_dict[k] = get_value(v)
            return sub_dict

    for line in response.splitlines():
        if line and not line.startswith('#'):
            if line.find(':') != -1:
                # Split, the info fields keys and values.
                # Note that the value may contain ':'. but the 'host:'
                # pseudo-command is the only case where the key contains ':'
                key, value = line.split(':', 1)
                if key == 'cmdstat_host':
                    key, value = line.rsplit(':', 1)

                if key == 'module':
                    # Hardcode a list for key 'modules' since there could be
                    # multiple lines that started with 'module'
                    info.setdefault('modules', []).append(get_value(value))
                else:
                    info[key] = get_value(value)
            else:
                # if the line isn't splittable, append it to the "__raw__" key
                info.setdefault('__raw__', []).append(line)
    return info


def monkeypatch_crc_ccitt():
    # crc < 7 only has the CCITT attr, crc >= 7 has XMODEM
    # for backward compatbility with this and python-redis we patch the enum
    # note that only pyredis >= 0.4.0 uses this. older versions use the crc16 library
    # and can be ignored
    try:
        import crc
    except ImportError:
        # no crc --> no monkeypatching
        return

    if not hasattr(crc.Crc16, 'CCITT') and hasattr(crc.Crc16, 'XMODEM'):
        crc.Crc16.CCITT = crc.Crc16.XMODEM
