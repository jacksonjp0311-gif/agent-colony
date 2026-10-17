import gzip

from colony import oeis_terms as O


def _gz(tmp_path):
    p = tmp_path / "stripped.gz"
    with gzip.open(p, "wt") as f:
        f.write("# header\n")
        f.write("A000045 ,0,1,1,2,3,5,8,13,21,34,55,89,144,233,377,610,987,\n")
        f.write("A000004 ,0,0,0,0,0,0,0,0,0,0,0,0,0,\n")
    return p


def test_build_and_lookup(tmp_path, monkeypatch):
    monkeypatch.setenv("COLONY_OEIS_CACHE", str(tmp_path / "c"))
    assert O.lookup([1, 2, 3]) == {"status": "unchecked", "anums": []}
    r = O.build(_gz(tmp_path))
    assert r["built"] and r["sequences"] == 2 and O.available()
    fib = [1, 1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144]
    assert O.lookup(fib) == {"status": "found", "anums": ["A000045"]}
    assert O.lookup(fib[1:])["status"] == "found"        # offsets differ: shifted windows match
    assert O.lookup([7, 1, 9, 4, 4, 2, 8, 6, 5, 3, 1, 0])["status"] == "not_found"
    assert O.lookup([0] * 12)["status"] == "too_simple"
    assert O.build(_gz(tmp_path))["built"] is False      # cached
