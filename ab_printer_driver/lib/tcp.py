# -*- coding: utf-8 -*-
"""TCP transport for thermal / network printers.

Thermal receipt printers (Epson TM-T, Star TSP, Bixolon SRP, Xprinter,
Citizen CT-S, …) accept a single TCP client at a time. When two callers
race on the same printer (POS tab + Printer Manager tab, kitchen ticket
+ receipt print, cron retry + operator test), the second connection is
refused / hangs / interleaves bytes. We serialise per (ip, port) with a
process-wide threading.Lock. Parallelism across DIFFERENT printers is
preserved.
"""
import logging
import socket
import threading
import time

_logger = logging.getLogger(__name__)

_PRINTER_LOCKS_GUARD = threading.Lock()
_PRINTER_LOCKS = {}  # (ip, port) -> threading.Lock
LOCK_TIMEOUT_S = 8.0
DEFAULT_TIMEOUT_S = 10.0


def lock_for(ip, port):
    """Return the singleton threading.Lock for this (ip, port)."""
    key = (str(ip), int(port))
    with _PRINTER_LOCKS_GUARD:
        lock = _PRINTER_LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _PRINTER_LOCKS[key] = lock
        return lock


def send_to_printer(printer_ip, printer_port, data, timeout=None):
    """Send raw bytes to a network printer via TCP, serialised per-printer.

    Returns:
        (success: bool, error: str|None, duration_s: float)
    """
    timeout = timeout if timeout is not None else DEFAULT_TIMEOUT_S
    start = time.time()
    lock = lock_for(printer_ip, printer_port)
    if not lock.acquire(timeout=LOCK_TIMEOUT_S):
        return False, f'Printer busy (held > {int(LOCK_TIMEOUT_S)}s)', time.time() - start
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect((printer_ip, int(printer_port)))
        sock.sendall(data)
        try:
            sock.shutdown(socket.SHUT_WR)
        except OSError:
            pass
        sock.close()
        return True, None, time.time() - start
    except socket.timeout:
        return False, 'Connection timeout', time.time() - start
    except ConnectionRefusedError:
        return False, 'Connection refused', time.time() - start
    except OSError as e:
        return False, str(e), time.time() - start
    except Exception as e:
        _logger.exception("send_to_printer crash %s:%s", printer_ip, printer_port)
        return False, str(e), time.time() - start
    finally:
        lock.release()


def probe(ip, port, timeout_s=0.5):
    """Pure TCP reachability probe (no data sent). Used by the scanner."""
    t0 = time.time()
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout_s)
        rc = sock.connect_ex((ip, int(port)))
        sock.close()
        if rc == 0:
            return True, (time.time() - t0) * 1000
        return False, (time.time() - t0) * 1000
    except Exception:
        return False, (time.time() - t0) * 1000
