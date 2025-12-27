import logging

from mlx_lm import generate, load

from app.logging_setup import setup_logging

setup_logging()
logger = logging.getLogger(__name__)

MODEL_NAME = "mlx-community/Qwen2.5-14B-Instruct-4bit"

def main():
    logger.info("Loading %s into Unified Memory...", MODEL_NAME)
    
    # This automatically leverages the M4's Neural Engine/GPU.
    model, tokenizer = load(MODEL_NAME, adapter_path="adapters")
    
    logger.info("Model loaded. Type 'quit' to exit.")
    logger.info("%s", "-" * 50)

    system_prompt = (
        "You are a helpful personal assistant for Ananya Singh. "
        "You know these user facts: Ananya Singh lives in New York City, "
        "enjoys eating out, likes drinking tea, loves sports, and his favorite team is the New York Giants. "
        "Be warm, practical, and concise. Do not invent personal data beyond what is provided."
    )
    
    messages = [{"role": "system", "content": system_prompt}]

    while True:
        user_input = input("\nYou: ")
        if user_input.lower() in ["quit", "exit"]:
            break

        # Format for Qwen 2.5 (ChatML format)
        messages.append({"role": "user", "content": user_input})
        
        # Apply the chat template to format the prompt correctly
        prompt = tokenizer.apply_chat_template(
            messages, 
            tokenize=False, 
            add_generation_prompt=True
        )

        # max_tokens: controls response length
        # temp: 0.7 is the "Goldilocks" zone for creativity vs precision
        response = generate(
            model, 
            tokenizer, 
            prompt=prompt, 
            verbose=False, 
            max_tokens=1024
        )

        logger.info("Assistant: %s", response)
        messages.append({"role": "assistant", "content": response})

if __name__ == "__main__":
    main()
