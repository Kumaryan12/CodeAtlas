FROM python:3.13-slim-bookworm@sha256:ed86c82274b3c69b52fb5820f358f0bd7df0b603332063cb5c6e32bd220c3e6e
LABEL codeatlas.profile="python-unittest-v1"
COPY unittest_runner.py /opt/codeatlas/unittest_runner.py
USER 65534:65534
WORKDIR /workspace
ENTRYPOINT ["/usr/bin/timeout", "--signal=KILL", "30s"]
CMD ["python", "-I", "-B", "/opt/codeatlas/unittest_runner.py"]
