"""Run one recommendation in a process that the executor can time out."""

import json
import sys

from app import ml


def main():
    job = json.load(sys.stdin)
    request = job["request"]
    model = request.pop("model")
    ml.decision.optimize(ml.run(model), request, job["output"])


if __name__ == "__main__":
    main()
