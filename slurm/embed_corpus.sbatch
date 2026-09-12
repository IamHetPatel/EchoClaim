#!/bin/bash
#SBATCH --job-name=echoclaim-embed
#SBATCH --partition=alpha          # TODO: set to your ZIH GPU partition (e.g. alpha/capella)
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --time=02:00:00
#SBATCH --output=logs/embed_%j.out

# Batch-embed the corpus (or the emb_v2 backfill) on a ZIH GPU.
# Makes the migration demo realistic at corpus scale instead of toy scale.

set -euo pipefail

module purge
module load release/24.04 GCCcore/12.3.0 Python/3.11.3   # TODO: match current ZIH modules
source "$HOME/envs/echoclaim/bin/activate"

export QDRANT_URL="${QDRANT_URL:?set QDRANT_URL to your reachable Qdrant}"
export EMBED_BATCH_SIZE=256
export HF_HOME="$HOME/.cache/huggingface"

VERSION="${1:-emb_v2}"

echo "Backfilling embedding version: ${VERSION}"
srun python -m retrieval.migrate backfill --to "${VERSION}"
echo "Done."
