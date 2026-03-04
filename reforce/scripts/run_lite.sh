#!/bin/bash
# Run ReFoRCE on Spider2-lite (SQLite) dataset
# Usage: bash scripts/run_lite.sh [model] [num_votes] [num_workers]

MODEL=${1:-"gpt-4o"}
NUM_VOTES=${2:-3}
NUM_WORKERS=${3:-8}
OUTPUT_DIR="output/${MODEL}-lite-log"

echo "Model: $MODEL | Votes: $NUM_VOTES | Workers: $NUM_WORKERS"
echo "Output: $OUTPUT_DIR"

# Step 1: Generate schema prompts from SQLite files
echo "[1/3] Generating schema prompts..."
python reconstruct_data.py \
    --example_folder examples \
    --add_description \
    --add_sample_rows

# Step 2: Run with voting
echo "[2/3] Running ReFoRCE with voting..."
python run.py \
    --task lite \
    --db_path examples \
    --output_path "$OUTPUT_DIR" \
    --model "$MODEL" \
    --pre_model "$MODEL" \
    --model_vote \
    --num_votes "$NUM_VOTES" \
    --num_workers "$NUM_WORKERS" \
    --max_iter 5

# Step 3: Collect results
echo "[3/3] Collecting results..."
python get_metadata.py \
    --result_path "$OUTPUT_DIR" \
    --output_path "output/${MODEL}-lite"

echo "Done. Results in output/${MODEL}-lite/"
