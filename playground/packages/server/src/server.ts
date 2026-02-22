import Fastify from 'fastify';
import cors from '@fastify/cors';
import websocket from '@fastify/websocket';
import type { ScenarioConfig } from '@ahv/hypervisor';
import { SCENARIOS, getScenario } from './scenarios.js';
import { runScenario } from './runner.js';

const PORT = 3001;

async function main() {
  const app = Fastify({ logger: true });

  await app.register(cors, { origin: true });
  await app.register(websocket);

  // Health check
  app.get('/health', async () => ({ status: 'ok', ts: Date.now() }));

  // List scenarios
  app.get('/api/scenarios', async () => SCENARIOS);

  // Get single scenario
  app.get<{ Params: { key: string } }>('/api/scenarios/:key', async (req, reply) => {
    const scenario = getScenario(req.params.key);
    if (!scenario) {
      reply.code(404);
      return { error: 'Scenario not found' };
    }
    return scenario;
  });

  // Run scenario (HTTP — returns full trace)
  app.post<{
    Body: {
      scenario: string;
      mode?: 'unsafe' | 'safe' | 'both';
      config?: Partial<ScenarioConfig>;
    };
  }>('/api/run', async (req, reply) => {
    const { scenario: key, mode = 'both', config: partialConfig } = req.body;
    const scenario = getScenario(key);
    if (!scenario) {
      reply.code(404);
      return { error: 'Scenario not found' };
    }

    const config: ScenarioConfig = {
      taintMode: partialConfig?.taintMode ?? 'by_default',
      capsPreset: partialConfig?.capsPreset ?? 'external-side-effects',
      policyStrictness: partialConfig?.policyStrictness ?? 'strict',
      canonOn: partialConfig?.canonOn ?? true,
    };

    const events: unknown[] = [];
    await runScenario({
      events: scenario.events,
      mode,
      config,
      emit: (event) => events.push(event),
    });

    return { scenario: key, mode, config, trace: events };
  });

  // WebSocket trace endpoint
  app.register(async function (fastify) {
    fastify.get('/trace', { websocket: true }, (socket) => {
      socket.on('message', async (raw: Buffer) => {
        let msg: {
          type: string;
          scenario: string;
          mode?: 'unsafe' | 'safe' | 'both';
          config?: Partial<ScenarioConfig>;
        };

        try {
          msg = JSON.parse(raw.toString());
        } catch {
          socket.send(JSON.stringify({ error: 'Invalid JSON' }));
          return;
        }

        if (msg.type !== 'run_scenario') {
          socket.send(JSON.stringify({ error: 'Unknown message type' }));
          return;
        }

        const scenario = getScenario(msg.scenario);
        if (!scenario) {
          socket.send(JSON.stringify({ error: 'Scenario not found' }));
          return;
        }

        const config: ScenarioConfig = {
          taintMode: msg.config?.taintMode ?? 'by_default',
          capsPreset: msg.config?.capsPreset ?? 'external-side-effects',
          policyStrictness: msg.config?.policyStrictness ?? 'strict',
          canonOn: msg.config?.canonOn ?? true,
        };

        // Send start marker
        socket.send(JSON.stringify({ type: 'run_start', scenario: msg.scenario }));

        await runScenario({
          events: scenario.events,
          mode: msg.mode ?? 'both',
          config,
          emit: (event) => {
            if (socket.readyState === 1) {
              socket.send(JSON.stringify(event));
            }
          },
        });

        // Send end marker
        if (socket.readyState === 1) {
          socket.send(JSON.stringify({ type: 'run_end', scenario: msg.scenario }));
        }
      });
    });
  });

  await app.listen({ port: PORT, host: '0.0.0.0' });
  console.log(`Agent Hypervisor server running on http://localhost:${PORT}`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
