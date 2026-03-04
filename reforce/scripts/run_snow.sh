#!/bin/bash
# Run ReFoRCE on Spider2-snow (Snowflake) dataset
# Requires: snowflake_credential.json in reforce/ directory
# Usage: bash scripts/run_snow.sh [model] [num_votes] [num_workers]

MODEL=${1:-"o1-preview"}
NUM_VOTES=${2:-3}
NUM_WORKERS=${3:-8}
SL_MODEL="gpt-4o"
OUTPUT_DIR="output/${MODEL}-snow-log"

echo "Model: $MODEL | SL Model: $SL_MODEL | Votes: $NUM_VOTES | Workers: $NUM_WORKERS"
echo "Output: $OUTPUT_DIR"

# Step 1: Reorganize folder structure for Snowflake
echo "[1/4] Reorganizing folder structure..."
python reconstruct_data.py \
    --example_folder examples \
    --make_folder

# Step 2: Generate schema prompts
echo "[2/4] Generating schema prompts with descriptions and sample rows..."
python reconstruct_data.py \
    --example_folder examples \
    --add_description \
    --add_sample_rows \
    --rm_digits

# Step 3: Schema linking (reduces table search space)
echo "[3/4] Running schema linking with $SL_MODEL..."
python run.py \
    --task snow \
    --db_path examples \
    --output_path "$OUTPUT_DIR" \
    --model "$MODEL" \
    --pre_model "$MODEL" \
    --schema_linking_model "$SL_MODEL" \
    --schema_linking_only \
    --num_workers "$NUM_WORKERS"

# Step 4: Run main inference with voting
echo "[4/4] Running ReFoRCE with voting..."
python run.py \
    --task snow \
    --db_path examples \
    --output_path "$OUTPUT_DIR" \
    --model "$MODEL" \
    --pre_model "$MODEL" \
    --model_vote \
    --num_votes "$NUM_VOTES" \
    --num_workers "$NUM_WORKERS" \
    --max_iter 5

# Collect results
python get_metadata.py \
    --result_path "$OUTPUT_DIR" \
    --output_path "output/${MODEL}-snow"

echo "Done. Results in output/${MODEL}-snow/"
