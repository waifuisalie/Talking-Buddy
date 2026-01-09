# Contributing to TalkingBuddy Voice Assistant

Thank you for your interest in contributing to TalkingBuddy! We welcome contributions from the community.

## How to Contribute

### Reporting Bugs

If you find a bug, please open an issue with:
- Clear description of the problem
- Steps to reproduce
- Expected vs actual behavior
- System information (RPi version, OS, Python version)
- Relevant logs or error messages

### Suggesting Features

Feature requests are welcome! Please:
- Check existing issues first to avoid duplicates
- Describe the feature and its use case
- Explain why it would be valuable to users
- Consider implementation complexity

### Pull Requests

1. **Fork the repository**
2. **Create a feature branch** (`git checkout -b feature/your-feature-name`)
3. **Make your changes**
4. **Test thoroughly** on Raspberry Pi 5 if possible
5. **Commit your changes** with clear, descriptive messages
6. **Push to your fork** (`git push origin feature/your-feature-name`)
7. **Open a Pull Request** with a clear description

## Development Guidelines

### Code Style

**Python:**
- Follow [PEP 8](https://www.python.org/dev/peps/pep-0008/) style guide
- Use type hints where appropriate
- Maximum line length: 100 characters
- Use docstrings for all functions and classes

**C/C++ (ESP32):**
- Follow [Google C++ Style Guide](https://google.github.io/styleguide/cppguide.html)
- Use meaningful variable and function names
- Comment complex logic
- Keep functions focused and concise

**Documentation:**
- Use clear, concise language
- Include code examples where helpful
- Update relevant documentation with code changes

### Testing

Before submitting a PR:
- Test on actual hardware if possible (RPi5, ESP32-S3)
- Verify all modes work: serial, keyboard, disabled
- Check Portuguese language quality in responses
- Ensure no regressions in existing functionality
- Test installation script on clean system

### Commit Messages

Write clear, descriptive commit messages:

```
Short summary (50 chars or less)

More detailed explanation if needed. Wrap at 72 characters.
Explain what changed and why, not just what you did.

- Bullet points are okay
- Use present tense ("Add feature" not "Added feature")
- Reference issues: "Fixes #123" or "Relates to #456"
```

## Project Structure

```
rpi5-chatbot/src/          # Python source code
├── config.py              # Configuration management
├── voice_chatbot.py       # Main controller
├── whisper_stt.py         # Speech-to-text
├── ollama_llm.py          # Language model
├── piper_tts.py           # Text-to-speech
└── ...

esp32-wake-word/src/       # ESP32 firmware
├── main.cpp               # Entry point
├── Application.cpp        # State machine
└── state_machine/         # Wake word detection
```

## Areas for Contribution

### Priority Areas

1. **Documentation**
   - Improve installation guides
   - Add troubleshooting tips
   - Create video tutorials
   - Translate to other languages

2. **Hardware Support**
   - Test on different Raspberry Pi models
   - Support alternative microphones
   - Optimize for lower-end hardware

3. **Features**
   - Additional language support
   - Improve Portuguese model quality
   - Web-based configuration interface
   - Better error handling

4. **Testing**
   - Unit tests for Python modules
   - Integration tests
   - Hardware compatibility testing

### Good First Issues

Look for issues labeled `good first issue` - these are:
- Well-defined and scoped
- Don't require deep system knowledge
- Good for learning the codebase

## Community

### Code of Conduct

- Be respectful and inclusive
- Welcome newcomers
- Focus on constructive feedback
- Assume good intentions

### Getting Help

- Read the documentation first
- Search existing issues
- Ask in issue comments
- Be patient and polite

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

---

Thank you for helping make TalkingBuddy better! 🎤🤖
