# webhook examples

## radarr

### webhook request example

```json
{
    "movie": {
        "id": 123,
        "title": "Movie",
        "year": 2019,
        "releaseDate": "2020-01-01",
        "folderPath": "/path/to/Movie",
        "tmdbId": 575776,
        "imdbId": "tt123"
    },
    "remoteMovie": {
        "tmdbId": 123,
        "imdbId": "tt123",
        "title": "Movie",
        "year": 2019
    },
    "movieFile": {
        "id": 371,
        "relativePath": "Movie.mp4",
        "path": "/data/Movie.mp4",
        "quality": "Bluray-1080p",
        "qualityVersion": 1,
        "releaseGroup": "RARBG",
        "sceneName": "Movie.2019.1080p.BluRay.H264.AAC-RARBG",
        "indexerFlags": "G_Freeleech",
        "size": 1727065263
    },
    "isUpgrade": false,
    "downloadId": "ABC123",
    "eventType": "Download",
}
```
