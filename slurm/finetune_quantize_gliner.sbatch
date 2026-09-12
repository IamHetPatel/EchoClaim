#!/bin/bash
#SBATCH --job-name=echoclaim-gliner
#SBATCH --partition=alpha          # TODO: your ZIH GPU partition
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=48G
#SBATCH --time=04:00:00
#SBATCH --output=logs/gliner_%j.out

# Re-fine-tune the GLiNER2 extractor on more claim data, then export an int8/ONNX
# serving artifact. A full fine-tune won't fit free Colab; an A100/H100 here is the

set -euo pipefail

module purge
module load release/24.04 GCCcore/12.3.0 Python/3.11.3   # TODO: match current ZIH modules
source "$HOME/envs/echoclaim/bin/activate"

DATA="${1:-extraction/data/claims_train.jsonl}"
OUT="${2:-extraction/artifacts/gliner2-ft}"

echo "Fine-tuning GLiNER2 on ${DATA}"
srun python extraction/finetune_gliner.py --data "${DATA}" --out "${OUT}"

echo "Quantizing to int8/ONNX for serving"
srun python extraction/quantize_gliner.py --model "${OUT}" --out "${OUT}-int8.onnx"

echo "Benchmark fp vs int8 (F1 / latency / cost)"
srun python extraction/benchmark.py --compare "${OUT}" "${OUT}-int8.onnx"
