"""Upload selected photographs to FTP, FTPS, or SFTP.
Passwords are held in memory for the transfer and are never saved to disk.
"""
from __future__ import annotations
from dataclasses import dataclass
from ftplib import FTP, FTP_TLS
from pathlib import Path
import posixpath
import time

@dataclass(frozen=True)
class Destination:
    protocol: str
    host: str
    username: str
    password: str
    directory: str = ""
    port: int = 0

def validate(destination):
    if destination.protocol not in ("FTP", "FTPS", "SFTP"):
        raise ValueError("Unsupported transfer protocol.")
    if not destination.host.strip() or not destination.username.strip():
        raise ValueError("A server and username are required.")
    if not (0 <= destination.port <= 65535):
        raise ValueError("Invalid server port.")
    directory = destination.directory.strip()
    if "\\x00" in directory or "\\r" in directory or "\\n" in directory:
        raise ValueError("Invalid remote directory.")
    return directory

def upload_files(paths, destination, progress=None, retries=2):
    """Upload in order; report completion only on successful server acknowledgement.

    Does not overwrite remote files deliberately: a destination may replace same-name
    files unless the server enforces unique names. Confirm remote directory beforehand.
    """
    directory = validate(destination)
    files = [Path(p) for p in paths]
    if not files or any(not p.is_file() for p in files):
        raise ValueError("Select existing photograph files to upload.")
    if len({p.name.casefold() for p in files}) != len(files):
        raise ValueError("Two selected files share a filename. Rename them before upload.")
    total = len(files)
    for index, path in enumerate(files, 1):
        for attempt in range(retries + 1):
            try:
                if destination.protocol == "SFTP":
                    _sftp_one(path, destination, directory)
                else:
                    _ftp_one(path, destination, directory)
                if progress: progress(index, total, path.name, None)
                break
            except Exception as exc:
                if attempt >= retries:
                    if progress: progress(index - 1, total, path.name, str(exc))
                    raise RuntimeError(f"Upload failed for {path.name}: {exc}") from exc
                time.sleep(min(2 ** attempt, 5))
    return total

def _ftp_one(path, dest, directory):
    ftp_class = FTP_TLS if dest.protocol == "FTPS" else FTP
    port = dest.port or 21
    with ftp_class() as client:
        client.connect(dest.host, port, timeout=30)
        client.login(dest.username, dest.password)
        if dest.protocol == 'FTPS':
            client.prot_p()  # encrypt the data channel as well as the login
        client.set_pasv(True)
        if directory: client.cwd(directory)
        with path.open("rb") as file:
            client.storbinary("STOR " + path.name, file, blocksize=128 * 1024)

def _sftp_one(path, dest, directory):
    try:
        import paramiko
    except ImportError as exc:
        raise RuntimeError("SFTP support requires the paramiko package.") from exc
    client = paramiko.SSHClient()
    client.load_system_host_keys()
    client.set_missing_host_key_policy(paramiko.RejectPolicy())
    try:
        client.connect(dest.host, port=dest.port or 22,
                       username=dest.username, password=dest.password,
                       look_for_keys=False, allow_agent=False, timeout=30)
        sftp = client.open_sftp()
        try:
            target = posixpath.join(directory, path.name) if directory else path.name
            sftp.put(str(path), target, confirm=True)
        finally:
            sftp.close()
    finally:
        client.close()
