# -*- coding: utf-8 -*-
import json
import os
import tempfile
import urllib.parse
import uuid

import requests


def generate_and_download_chart(title, labels, values, chart_type="bar", filename=None):
    """Generate a chart image via QuickChart and save it locally."""
    colors = [
        "rgba(54, 162, 235, 0.8)",
        "rgba(255, 99, 132, 0.8)",
        "rgba(255, 206, 86, 0.8)",
        "rgba(75, 192, 192, 0.8)",
    ]

    chart_config = {
        "type": chart_type,
        "data": {
            "labels": labels,
            "datasets": [
                {
                    "label": title,
                    "data": values,
                    "backgroundColor": colors[: len(labels)],
                    "borderWidth": 1,
                }
            ],
        },
        "options": {
            "plugins": {
                "title": {"display": True, "text": title, "font": {"size": 18}},
                "datalabels": {"display": True, "align": "end", "anchor": "end"},
            }
        },
    }

    encoded_config = urllib.parse.quote(json.dumps(chart_config))
    url = (
        "https://quickchart.io/chart"
        f"?c={encoded_config}&w=600&h=350&bkg=transparent&retina=true"
    )

    if not filename:
        filename = os.path.join(
            tempfile.gettempdir(), f"temp_chart_{uuid.uuid4().hex}.png"
        )

    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            with open(filename, "wb") as f:
                f.write(response.content)
            return filename
    except Exception as e:
        print(f"[chart] api failed: {e}")

    return None
