"""
Copy locked Chrome cookies DB + decrypt into cookies.txt for yt-dlp.
Runs while Chrome is open — no need to close the browser.

Works for Chrome 127+ on Windows (App Bound Encryption v20 — for v10/v11 cookies only;
v20-encrypted cookies require Chrome's elevation service and won't decrypt here.
But login cookies for YouTube are typically v10 even in Chrome 147.)

Usage: run from project root, writes ./cookies.txt
"""
import ctypes, ctypes.wintypes, os, shutil, json, base64, sqlite3, glob, sys, io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(PROJECT_ROOT)

GENERIC_READ = 0x80000000
FILE_SHARE_READ = 0x1; FILE_SHARE_WRITE = 0x2; FILE_SHARE_DELETE = 0x4
OPEN_EXISTING = 3
kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)


def copy_locked(src, dst):
    handle = kernel32.CreateFileW(
        src, GENERIC_READ,
        FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
        None, OPEN_EXISTING, 0, None
    )
    if handle == -1:
        raise OSError(f"Cannot open {src}: error {ctypes.get_last_error()}")
    try:
        buf = ctypes.create_string_buffer(65536)
        br = ctypes.wintypes.DWORD()
        with open(dst, 'wb') as f:
            while True:
                ok = kernel32.ReadFile(handle, buf, 65536, ctypes.byref(br), None)
                if not ok or br.value == 0:
                    break
                f.write(buf.raw[:br.value])
    finally:
        kernel32.CloseHandle(handle)


def get_chrome_key(local_state_path):
    with open(local_state_path, encoding='utf-8') as f:
        ls = json.load(f)
    key_b64 = ls['os_crypt']['encrypted_key']
    encrypted_key = base64.b64decode(key_b64)[5:]  # strip DPAPI prefix
    # Decrypt with Windows DPAPI
    import ctypes
    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", ctypes.wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]
    p = ctypes.create_string_buffer(encrypted_key, len(encrypted_key))
    blobin = DATA_BLOB(ctypes.sizeof(p), p)
    blobout = DATA_BLOB()
    retval = ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(blobin), None, None, None, None, 0, ctypes.byref(blobout))
    if not retval:
        raise RuntimeError("DPAPI decryption failed")
    return ctypes.string_at(blobout.pbData, blobout.cbData)


def decrypt_cookie(encrypted_value, key):
    if encrypted_value[:3] == b'v10' or encrypted_value[:3] == b'v11':
        from Crypto.Cipher import AES
        nonce = encrypted_value[3:3+12]
        ciphertext = encrypted_value[3+12:-16]
        tag = encrypted_value[-16:]
        cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
        return cipher.decrypt_and_verify(ciphertext, tag).decode('utf-8', errors='replace')
    return encrypted_value.decode('utf-8', errors='replace')


def export_cookies_txt(cookies_db, key, output_path, domain='.youtube.com'):
    conn = sqlite3.connect(cookies_db)
    cur = conn.cursor()
    cur.execute("""
        SELECT host_key, path, is_secure, expires_utc, name, encrypted_value
        FROM cookies
        WHERE host_key LIKE '%youtube.com' OR host_key LIKE '%google.com'
        OR host_key LIKE '%googleapis.com' OR host_key LIKE '%gstatic.com'
    """)
    rows = cur.fetchall()
    conn.close()

    written = 0
    skipped = 0
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("# Netscape HTTP Cookie File\n")
        f.write("# Exported by chrome_cookies_helper.py\n\n")
        for host, path, secure, expires, name, enc_val in rows:
            try:
                value = decrypt_cookie(enc_val, key) if enc_val else ''
                # Skip cookies with non-printable/binary characters
                if any(ord(c) < 32 for c in value):
                    skipped += 1
                    continue
                secure_flag = 'TRUE' if secure else 'FALSE'
                unix_exp = (expires - 11644473600000000) // 1000000 if expires else 0
                if unix_exp < 0:
                    unix_exp = 0
                f.write(f"{host}\tTRUE\t{path}\t{secure_flag}\t{unix_exp}\t{name}\t{value}\n")
                written += 1
            except Exception:
                skipped += 1
    print(f"  Written: {written}, Skipped (binary/error): {skipped}")
    return written


def main():
    # Find Chrome profile with YouTube cookies
    chrome_user_data = os.path.expandvars(r'%LOCALAPPDATA%\Google\Chrome\User Data')
    local_state = os.path.join(chrome_user_data, 'Local State')

    # Find the profile that has YouTube cookies
    profiles = glob.glob(os.path.join(chrome_user_data, '*', 'Network', 'Cookies'))
    best_profile = None
    best_count = 0
    for p in profiles:
        try:
            tmp = p + '.tmp_check'
            copy_locked(p, tmp)
            conn = sqlite3.connect(tmp)
            cur = conn.cursor()
            # Look for login cookies specifically
            cur.execute("""SELECT COUNT(*) FROM cookies
                WHERE host_key LIKE '%youtube.com'
                AND name IN ('LOGIN_INFO','SID','SSID','HSID','APISID','SAPISID','__Secure-1PSID','__Secure-3PSID')""")
            count = cur.fetchone()[0]
            conn.close()
            os.remove(tmp)
            if count > best_count:
                best_count = count
                best_profile = p
        except Exception:
            pass

    if not best_profile:
        print("No Chrome profile with YouTube cookies found")
        sys.exit(1)

    print(f"Using profile: {best_profile} ({best_count} YouTube cookies)")

    # Copy the cookies database
    cookies_copy = os.path.join(PROJECT_ROOT, "chrome_live_cookies.db")
    copy_locked(best_profile, cookies_copy)
    print(f"Copied cookies DB ({os.path.getsize(cookies_copy)} bytes)")

    # Get encryption key
    try:
        key = get_chrome_key(local_state)
        print(f"Got encryption key ({len(key)} bytes)")
    except Exception as e:
        print(f"Key error: {e}")
        sys.exit(1)

    # Check for pycryptodome
    try:
        from Crypto.Cipher import AES
    except ImportError:
        print("Installing pycryptodome...")
        import subprocess
        subprocess.run([sys.executable, '-m', 'pip', 'install', 'pycryptodome', '-q'])
        from Crypto.Cipher import AES

    # Export to cookies.txt
    output = os.path.join(PROJECT_ROOT, "cookies.txt")
    written = export_cookies_txt(cookies_copy, key, output)
    print(f"Exported {written} cookies to cookies.txt")
    os.remove(cookies_copy)


if __name__ == '__main__':
    main()
