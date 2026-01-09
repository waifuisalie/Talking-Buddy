"""
Language Model module using Ollama
"""

import requests
import json
from typing import Optional, List, Dict, Any
import config

class OllamaLLM:
    """Handles language model inference using Ollama"""

    def __init__(self, ollama_config: config.OllamaConfig):
        self.config = ollama_config
        self.conversation_history: List[Dict[str, str]] = []

    def generate_response(self, prompt: str, system_prompt: Optional[str] = None, max_retries: int = 2) -> Optional[str]:
        """Generate a response from the language model with retry logic using /chat endpoint"""
        for attempt in range(max_retries + 1):
            try:
                # Build messages for chat endpoint
                messages = self._build_messages(prompt, system_prompt)

                payload = {
                    "model": self.config.model,
                    "messages": messages,
                    "stream": False,
                    "options": {
                        "temperature": self.config.temperature,
                        "num_predict": self.config.max_tokens,
                    }
                }

                print(f"🤖 Sending to Ollama ({self.config.model})..." + (f" (attempt {attempt + 1})" if attempt > 0 else ""))
                print(f"📝 User message (len={len(prompt)}): '{prompt[:100]}{'...' if len(prompt) > 100 else ''}'")

                response = requests.post(
                    self.config.url,
                    json=payload,
                    timeout=self.config.timeout
                )

                if response.status_code == 200:
                    result = response.json()
                    ai_response = result.get("message", {}).get("content", "").strip()

                    if ai_response:
                        # Clean up the response
                        clean_response = self._clean_response(ai_response)

                        # Update conversation history
                        self._add_to_history("user", prompt)
                        self._add_to_history("assistant", clean_response)

                        print(f"🤖 AI Response: {clean_response}")
                        return clean_response
                    else:
                        print("❌ Empty response from Ollama")
                        if attempt < max_retries:
                            print("🔄 Retrying...")
                            continue
                        return "I'm sorry, I couldn't generate a response."

                elif response.status_code == 500 and attempt < max_retries:
                    # Model runner crashed, try warming up again
                    print("🔄 Model runner stopped, attempting to restart...")
                    if self.warm_up_model():
                        print("🔄 Retrying request...")
                        continue
                    else:
                        print("❌ Failed to restart model")
                        break
                else:
                    print(f"❌ Ollama error: {response.status_code} - {response.text}")
                    if attempt < max_retries:
                        print("🔄 Retrying...")
                        continue
                    return "Sorry, I'm having trouble processing your request right now."

            except requests.exceptions.Timeout:
                print(f"❌ Ollama request timed out (attempt {attempt + 1})")
                if attempt < max_retries:
                    print("🔄 Retrying...")
                    continue
                return "Sorry, I'm taking too long to respond. Please try again."

            except requests.exceptions.ConnectionError:
                print("❌ Cannot connect to Ollama server")
                return "Sorry, I can't connect to my language model. Please check if Ollama is running."

            except Exception as e:
                print(f"❌ Error with Ollama: {e}")
                if attempt < max_retries:
                    print("🔄 Retrying...")
                    continue
                return "Sorry, I encountered an error while processing your request."

        return "Sorry, I couldn't process your request after multiple attempts."

    def generate_streaming_response(self, prompt: str, system_prompt: Optional[str] = None):
        """Generate a streaming response from the language model using /chat endpoint"""
        try:
            messages = self._build_messages(prompt, system_prompt)

            payload = {
                "model": self.config.model,
                "messages": messages,
                "stream": True,
                "options": {
                    "temperature": self.config.temperature,
                    "num_predict": self.config.max_tokens
                }
            }

            response = requests.post(
                self.config.url,
                json=payload,
                timeout=self.config.timeout,
                stream=True
            )

            if response.status_code == 200:
                full_response = ""
                for line in response.iter_lines():
                    if line:
                        data = json.loads(line)
                        if 'message' in data and 'content' in data['message']:
                            chunk = data['message']['content']
                            full_response += chunk
                            yield chunk

                        if data.get('done', False):
                            break

                # Update conversation history with complete response
                if full_response.strip():
                    clean_response = self._clean_response(full_response)
                    self._add_to_history("user", prompt)
                    self._add_to_history("assistant", clean_response)

        except Exception as e:
            print(f"❌ Error with streaming Ollama: {e}")
            yield "Sorry, I encountered an error while processing your request."

    def _build_messages(self, user_input: str, system_prompt: Optional[str] = None) -> List[Dict[str, str]]:
        """Build messages array for /chat endpoint"""
        messages = []

        # Only add system message if provided and non-empty
        if system_prompt and system_prompt.strip():
            messages.append({
                "role": "system",
                "content": system_prompt
            })

        # Add user message
        messages.append({
            "role": "user",
            "content": user_input
        })

        return messages

    def _clean_response(self, response: str) -> str:
        """Clean up the AI response"""
        # Basic cleaning for base model output
        response = response.strip()

        # Remove excessive whitespace
        response = " ".join(response.split())

        # Ensure it doesn't end with incomplete words or artifacts
        if response.endswith(("...", "…")):
            response = response[:-3].strip()

        return response

    def _add_to_history(self, role: str, content: str):
        """Add entry to conversation history"""
        self.conversation_history.append({
            "role": role,
            "content": content
        })

        # Keep history manageable
        max_history = 20  # 10 exchanges
        if len(self.conversation_history) > max_history:
            self.conversation_history = self.conversation_history[-max_history:]

    def clear_history(self):
        """Clear conversation history"""
        self.conversation_history.clear()
        print("🧹 Conversation history cleared")

    def get_history(self) -> List[Dict[str, str]]:
        """Get conversation history"""
        return self.conversation_history.copy()

    def set_history(self, history: List[Dict[str, str]]):
        """Set conversation history"""
        self.conversation_history = history

    def warm_up_model(self) -> bool:
        """Warm up the model by making a simple request"""
        try:
            print(f"🔥 Warming up model '{self.config.model}'...")

            warm_up_payload = {
                "model": self.config.model,
                "messages": [
                    {"role": "user", "content": "Hi"}
                ],
                "stream": False,
                "options": {
                    "num_predict": 1,
                    "temperature": 0.1
                }
            }

            response = requests.post(
                self.config.url,
                json=warm_up_payload,
                timeout=30  # Give more time for initial load
            )

            if response.status_code == 200:
                print(f"✅ Model '{self.config.model}' warmed up successfully")
                return True
            else:
                print(f"❌ Failed to warm up model: {response.status_code}")
                return False

        except Exception as e:
            print(f"❌ Error warming up model: {e}")
            return False

    def is_available(self) -> bool:
        """Check if Ollama service is available"""
        try:
            # First check if server is running
            health_check = requests.get("http://localhost:11434/api/tags", timeout=5)
            if health_check.status_code != 200:
                return False

            # Check if our model is listed
            models = health_check.json().get("models", [])
            model_names = [m["name"] for m in models]

            if f"{self.config.model}:latest" not in model_names and self.config.model not in model_names:
                print(f"❌ Model '{self.config.model}' not found in available models")
                return False

            # Try to warm up the model
            return self.warm_up_model()

        except Exception as e:
            print(f"❌ Error checking Ollama availability: {e}")
            return False

    def get_model_info(self) -> Optional[Dict[str, Any]]:
        """Get information about the current model"""
        try:
            # Ollama API endpoint for model info
            model_url = f"http://localhost:11434/api/show"
            payload = {"name": self.config.model}

            response = requests.post(model_url, json=payload, timeout=10)

            if response.status_code == 200:
                return response.json()
            else:
                return None

        except Exception as e:
            print(f"❌ Error getting model info: {e}")
            return None