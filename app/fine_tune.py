'''
mlx_lm.lora \
    --model mlx-community/Qwen2.5-14B-Instruct-4bit \
    --data data \
    --train \
    --fine-tune-type lora \
    --batch-size 1 \
    --grad-checkpoint \
    --num-layers 16 \
    --iters 600 \
    --learning-rate 1e-5 \
    --adapter-path adapters
'''