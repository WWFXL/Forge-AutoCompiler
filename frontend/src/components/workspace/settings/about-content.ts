/**
 * About Forge markdown content. Inlined to avoid raw-loader dependency
 * (Turbopack cannot resolve raw-loader for .md imports).
 */
export const aboutMarkdown = `
# About Forge

**From Open Source, Back to Open Source**

Forge is an open-source automated code compilation system that orchestrates sub-agents, memory, and sandboxes to build, test, and compile code.

## Core Features

- **Automated Compilation**: Build, test, and compile code in isolated Docker containers.
- **Sub-Agents**: Sub-Agents help the main agent to handle complex multi-step compilation tasks.
- **Sandbox & File System**: Safely execute code and manipulate files in the sandbox.
- **Artifact Verification**: Deterministic validation of build outputs.
- **Long-Term Memory**: Keep recording the user's profile, top of mind, and conversation history.

## GitHub Repository

Explore Forge on GitHub: [github.com/your-org/forge](https://github.com/your-org/forge)

## License

Forge is proudly open source and distributed under the MIT License.

## Acknowledgments

We extend our heartfelt gratitude to the open source projects and contributors who have made Forge a reality. We truly stand on the shoulders of giants.

### Core Frameworks

- **LangChain**: A phenomenal framework that powers our LLM interactions and chains.
- **LangGraph**: Enabling sophisticated multi-agent orchestration.
- **Next.js**: A cutting-edge framework for building web applications.

### UI Libraries

- **Shadcn**: Minimalistic components that power our UI.
- **SToneX**: For his invaluable contribution to token-by-token visual effects.

These outstanding projects form the backbone of Forge and exemplify the transformative power of open source collaboration.
`;