Act as a senior software engineer and deployment specialist. Analyze this entire project and make it runnable, production-ready, and prepared for deployment.

Your tasks:

1. Understand the project
- Inspect the complete directory structure and important files.
- Identify the programming languages, frameworks, databases, package managers, build tools, and external services.
- Explain what the application does and how its main components work.
- Locate the frontend, backend, API routes, database code, configuration, and entry points.
- Check for project-specific instructions such as README, AGENTS.md, Docker files, and CI configuration.

2. Make it runnable
- Determine the correct installation, development, build, test, and production commands.
- Fix missing dependencies, broken imports, configuration problems, build errors, runtime errors, and incompatible package versions.
- Do not unnecessarily rewrite working code or change the intended behavior.
- Preserve existing user changes and secrets.
- Run the application and verify its important functionality.
- Run relevant tests, linting, type-checking, and production builds.
- If no tests exist, perform practical smoke tests.

3. Configure environment variables
- Identify every required environment variable.
- Create or update `.env.example` with safe placeholder values.
- Never expose or commit real credentials.
- Add appropriate entries to `.gitignore`.
- Explain where each production secret must be configured.

4. Prepare it for production
- Ensure the application uses production-safe configuration.
- Add appropriate start and build scripts.
- Configure the application to use the platform-provided port and host.
- Review security, error handling, logging, CORS, database connections, migrations, static files, and health checks.
- Add a Dockerfile only if it materially improves deployment.
- Create any necessary deployment configuration files.
- Keep changes minimal, maintainable, and consistent with the existing architecture.

5. Recommend a deployment platform
- Research the currently available free or no-cost deployment options suitable for this exact stack.
- Compare at least three suitable platforms based on:
  - free-tier limitations
  - sleep or cold-start behavior
  - bandwidth and build limits
  - database support
  - custom domains
  - deployment difficulty
  - whether a payment card is required
- Prefer official platform documentation as sources.
- Recommend one primary platform and explain why it best fits this project.
- If the frontend and backend should be deployed separately, provide the best free option for each.
- Do not claim a platform is free without verifying its current pricing and limits.

6. Prepare deployment instructions
- Write a clear README section containing:
  - prerequisites
  - local setup
  - environment-variable setup
  - development commands
  - testing and build commands
  - production startup
  - database migration or seeding steps
  - exact deployment instructions
  - post-deployment verification
  - rollback guidance

7. Verification
- Actually execute the relevant installation, test, lint, build, and startup commands when tools are available.
- Do not report success unless the command genuinely succeeds.
- Test a health endpoint or important application route.
- Clearly distinguish verified results from assumptions.
- If blocked by a missing credential or external service, continue with everything else and tell me exactly what I need to provide.

Before editing:
- Briefly summarize the architecture.
- List the problems you discovered.
- Present a concise implementation plan.

Then implement the fixes autonomously. Ask me a question only if a missing decision would materially change the application or cause an irreversible action.

At the end, provide:
- architecture summary
- files changed
- problems fixed
- commands executed and their results
- remaining issues or risks
- required environment variables
- recommended free deployment platform
- exact deployment steps
- final deployment checklist