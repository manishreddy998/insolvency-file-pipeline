#!/bin/sh
# Start Ollama, fetch the small open model once, register it, then mark ready.
set -e
rm -f /root/.ollama/ready
ollama serve &
PID=$!
for i in $(seq 1 60); do ollama list >/dev/null 2>&1 && break; sleep 1; done
if ! ollama list | grep -q "^${MODEL_NAME}"; then
  if [ ! -s "/models/${MODEL_FILE}" ]; then
    echo "fetching ${MODEL_FILE}"
    apt-get update >/dev/null 2>&1 && apt-get install -y curl >/dev/null 2>&1 || true
    curl -fL -o "/models/${MODEL_FILE}.part" "${MODEL_URL}" && mv "/models/${MODEL_FILE}.part" "/models/${MODEL_FILE}"
  fi
  printf 'FROM /models/%s\nPARAMETER temperature 0.1\nPARAMETER num_ctx 4096\nPARAMETER num_predict 128\n' "${MODEL_FILE}" > /tmp/Modelfile
  ollama create "${MODEL_NAME}" -f /tmp/Modelfile
fi
# warm the model so the first question is not slow
timeout 120 ollama run "${MODEL_NAME}" "Reply with the single word OK." >/dev/null 2>&1 || true
touch /root/.ollama/ready
wait $PID
