from typing import Dict, List, Optional
import os
from loguru import logger
from groq import Groq

class Generator:
    """Generates responses using a Groq API language model."""
    
    def __init__(self, config: Dict):
        self.config = config
        # Use updated config keys
        self.model_name = config.get("groq_model_name", "llama3-8b-8192") 
        self.max_tokens = config.get("max_tokens", 1024) 
        self.temperature = config.get("temperature", 0.7)
        self.top_p = config.get("top_p", 1.0)
        
        # Initialize Groq client
        # API key is automatically read from GROQ_API_KEY env var by the client
        try:
            self.client = Groq()
            logger.info(f"Groq client initialized. Using model: {self.model_name}")
        except Exception as e:
             # The client might raise an error if API key is missing
             logger.error(f"Failed to initialize Groq client: {e}")
             logger.error("Please ensure the GROQ_API_KEY environment variable is set.")
             # Depending on desired behavior, you might want to raise the error
             # raise e 
             self.client = None # Set client to None to indicate failure

        # Remove local model/tokenizer init
        # self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
        # self.model = AutoModelForCausalLM.from_pretrained(self.model_name)
    
    def generate(self, prompt: str) -> str:
        """Generate a response for the given prompt using Groq API."""
        if not self.client:
             logger.error("Groq client not initialized. Cannot generate response.")
             return "I apologize, but I encountered an internal configuration error."
             
        try:
            logger.debug(f"Sending prompt to Groq ({self.model_name}):\n{prompt}")
            # Use Groq's chat completions endpoint
            chat_completion = self.client.chat.completions.create(
                messages=[
                    {
                        "role": "system",
                        "content": "You are a helpful assistant answering questions based on the provided context."
                    },
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ],
                model=self.model_name,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                top_p=self.top_p,
                stop=None, # Optional: sequences to stop generation at
                stream=False,
            )

            response_content = chat_completion.choices[0].message.content
            logger.debug(f"Received response from Groq: {response_content}")
            return response_content.strip()
            
        except Exception as e:
            logger.exception(f"Error generating response via Groq: {str(e)}") # Use logger.exception
            return "I apologize, but I'm having trouble generating a response at the moment."
    
    def format_prompt(self, query: str, context: str) -> str:
        """Format the prompt with query and context for the LLM."""
        # This prompt structure works well for instruction-following models
        return f"""Use the following context to answer the question at the end.
If the answer is not present in the context, say 'I do not have information about that based on the provided context.'
Do not make up information.

Context:
------
{context}
------

Question: {query}

Answer:""" 