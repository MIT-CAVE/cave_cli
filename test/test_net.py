import pytest
from cave_cli.utils.net import parse_ip_port


def test_valid_address():
    result = parse_ip_port("192.168.1.1:8000")
    assert result == ("192.168.1.1", 8000)


def test_valid_address_localhost():
    result = parse_ip_port("0.0.0.0:8080")
    assert result == ("0.0.0.0", 8080)


def test_valid_address_five_digit_port():
    result = parse_ip_port("10.0.0.1:65535")
    assert result == ("10.0.0.1", 65535)


def test_invalid_no_port():
    assert parse_ip_port("192.168.1.1") is None


def test_invalid_short_port():
    assert parse_ip_port("192.168.1.1:80") is None


def test_invalid_hostname():
    assert parse_ip_port("localhost:8000") is None


def test_invalid_empty():
    assert parse_ip_port("") is None
