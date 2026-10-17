/** Read-only operator control audit. No database writes, no browser dependencies. */
export const LIFECYCLE_COMMANDS = Object.freeze({
  "Não iniciado": ["start"],
  "Em execução": ["pause", "stop"],
  "Pausando": ["stop"],
  "Pausado": ["resume", "stop"],
  "Parando": [],
  "Parado": ["restart"],
  "Aguardando ativação segura": [],
});

const UUID = /^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i;
const LABELS = {
  start: "Iniciar projeto",
  pause: "Pausar",
  resume: "Retomar",
  stop: "Parar",
  restart: "Reiniciar",
};

export function validateProjectLifecycleReadOnly({heading, forms, expectedProjectKey}) {
  if (typeof heading !== "string" || typeof expectedProjectKey !== "string" ||
      !/^[a-z0-9][a-z0-9-]{0,63}$/.test(expectedProjectKey)) {
    throw new Error("invalid lifecycle heading or expected project key");
  }
  const match = /^Execução do projeto:\s*(.+)$/.exec(heading.trim());
  const stateLabel = match?.[1];
  if (!Object.hasOwn(LIFECYCLE_COMMANDS, stateLabel)) {
    throw new Error("unknown project execution state: " + String(stateLabel));
  }
  if (!Array.isArray(forms)) throw new Error("invalid lifecycle forms");
  const actual = forms.map(form => form?.command);
  const expected = LIFECYCLE_COMMANDS[stateLabel];
  if (JSON.stringify([...actual].sort()) !== JSON.stringify([...expected].sort())) {
    throw new Error("lifecycle command/state mismatch: " + stateLabel + " => " + JSON.stringify(actual));
  }
  const versions = new Set();
  const identities = new Set();
  for (const form of forms) {
    if (form?.projectKey !== expectedProjectKey || !Object.hasOwn(LABELS, form?.command) ||
        typeof form?.label !== "string" || form.label.trim() !== LABELS[form.command] ||
        typeof form?.version !== "string" || !/^(0|[1-9][0-9]*)$/.test(form.version) ||
        !Number.isSafeInteger(Number(form.version)) ||
        typeof form?.commandId !== "string" || !UUID.test(form.commandId) ||
        identities.has(form.commandId.toLowerCase())) {
      throw new Error("invalid project/version/command/idempotency identity");
    }
    identities.add(form.commandId.toLowerCase());
    versions.add(form.version);
  }
  if (versions.size > 1) throw new Error("inconsistent lifecycle control versions");
  return {
    stateLabel,
    availableCommands: [...actual].sort(),
    version: forms[0]?.version ?? null,
    verifiedWithoutMutation: true,
  };
}
