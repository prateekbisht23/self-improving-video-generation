"""Upload -> background processing -> structured results (Phase 1 exit criteria)."""

import pytest

from tests.integration.conftest import upload


def test_project_crud(client):
    r = client.post("/projects", json={"title": "Launch teaser", "description": "Europa clip"})
    assert r.status_code == 201
    pid = r.json()["id"]
    assert client.get(f"/projects/{pid}").json()["title"] == "Launch teaser"
    assert [p["id"] for p in client.get("/projects").json()] == [pid]
    assert client.get("/projects/00000000-0000-0000-0000-000000000000").status_code == 404


def test_upload_triggers_processing_and_produces_scenes(client, project, synthetic):
    r = upload(client, project["id"], synthetic / "cuts.mp4")
    assert r.status_code == 201, r.text
    asset = client.get(f"/assets/{r.json()['id']}").json()

    assert asset["status"] == "ready", asset["last_error"]
    assert (asset["width"], asset["height"], asset["aspect_ratio"]) == (1280, 720, "16:9")
    stages = {s["name"]: s["status"] for s in asset["stages"]}
    assert stages == {"probe": "done", "scenes": "done", "audio": "done", "transcript": "done",
                      "frames": "done", "visual": "skipped", "index": "done"}

    scenes = client.get(f"/assets/{asset['id']}/scenes").json()
    assert [s["index"] for s in scenes] == [0, 1, 2]                      # ordered
    assert scenes[1]["start"] == pytest.approx(4.0, abs=0.1)
    assert all(0 <= s["start"] < s["end"] <= asset["duration"] + 1e-3 for s in scenes)


def test_speech_is_transcribed_with_timestamps_and_searchable(client, project, synthetic):
    if not (synthetic / "speech.mp4").exists():
        pytest.skip("needs macOS `say`")
    aid = upload(client, project["id"], synthetic / "speech.mp4").json()["id"]
    segs = client.get(f"/assets/{aid}/transcript").json()
    assert segs and all(w["start"] <= w["end"] for s in segs for w in s["words"])
    assert "editing lab" in " ".join(s["text"] for s in segs).lower()

    scene = client.get(f"/assets/{aid}/scenes").json()[0]
    assert scene["speech_ratio"] > 0.5 and "transcription" in scene["transcript_text"].lower()

    hits = client.get(f"/projects/{project['id']}/search", params={"q": "transcription", "mode": "keyword"}).json()
    assert hits and hits[0]["scene"]["asset_id"] == aid and hits[0]["matched_by"] == ["keyword"]

    ctx = client.get(f"/assets/{aid}/context").json()  # rebuilt purely from the DB
    assert ctx["language"] == "en" and ctx["scenes"][0]["transcript"]


@pytest.mark.parametrize("name, content, status, msg", [
    ("notes.txt", b"hello", 415, "unsupported file type"),
    ("fake.mp4", b"definitely not a video", 422, "not a readable video"),
    ("empty.mp4", b"", 422, "empty file"),
])
def test_invalid_uploads_rejected(client, project, name, content, status, msg):
    r = client.post(f"/projects/{project['id']}/assets", files={"file": (name, content)})
    assert r.status_code == status and msg in r.json()["detail"]


def test_audio_only_file_rejected(client, project, tmp_path):
    from perception.ffmpeg import ffmpeg

    wav = tmp_path / "tone.mp4"
    ffmpeg("-f", "lavfi", "-i", "sine=duration=2", "-c:a", "aac", str(wav))
    r = upload(client, project["id"], wav)
    assert r.status_code == 422 and "no video stream" in r.json()["detail"]
