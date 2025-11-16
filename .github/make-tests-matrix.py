import re
from urllib import request


jobs = [
    # Blender 4 test first and last patch version of each minor version
    {
        "version": "4.2.0",
        "version_x_y": "4.2",
        "sha": "released",
        "download_url": "https://download.blender.org/release/Blender4.2/blender-4.2.0-linux-x64.tar.xz",
    },
    {  # LTS
        "version": "4.2.13",
        "version_x_y": "4.2",
        "sha": "released",
        "download_url": "https://download.blender.org/release/Blender4.2/blender-4.2.13-linux-x64.tar.xz",
    },
    {  # LTS
        "version": "4.5.2",
        "version_x_y": "4.5",
        "sha": "released",
        "download_url": "https://download.blender.org/release/Blender4.5/blender-4.5.2-linux-x64.tar.xz",
    },
    # {'version': '', 'version_x_y': '', 'download_url': ''},
]


def get_daily_builds(jobs: list):
    resp = request.urlopen("https://builder.blender.org/download/daily/")
    page = resp.read().decode("utf-8")
    releases = re.findall(
        r"(https://cdn.builder.blender.org/download/daily/blender-(((?:4|5)\.\d)\.\d-\w+)\+\S{1,6}\.(\S{12})-linux\.x86_64-release\.tar\.xz)",
        page,
    )
    for release in releases:
        new_job = {
            "version": release[1],
            "version_x_y": release[2],
            "download_url": release[0],
            "sha": release[3],
        }
        if new_job["version"].removesuffix("-stable") not in [
            job["version"] for job in jobs
        ]:
            jobs.append(new_job)


get_daily_builds(jobs)
matrix = {"include": jobs}
print(f"matrix={matrix}")