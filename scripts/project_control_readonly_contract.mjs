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

// V2 keeps actual worker observation separate from the administrative control.
const CONTROL_LABELS = Object.freeze({
  draft:"Não iniciado", pausing:"Pausando", paused:"Pausado", stopping:"Parando",
  stopped:"Parado", unavailable:"Aguardando ativação segura",
});
const RUN_LABELS = Object.freeze({
  running:"Desenvolvendo", recorded:"Pedido na fila", idle:"Sem execução ativa",
  unavailable:"Execução não verificável",
});
const RECOVERY_STATES = new Set(["eligible","not_eligible","unavailable"]);
const LABELS = {
  start: "Iniciar projeto",
  pause: "Pausar",
  resume: "Retomar",
  stop: "Parar",
  restart: "Reiniciar",
};

export function validateProjectLifecycleReadOnly({heading, forms, expectedProjectKey, controlState=null, workObservation=null, recoveryEligibility=null}) {
  if (typeof heading !== "string" || typeof expectedProjectKey !== "string" ||
      !/^[a-z0-9][a-z0-9-]{0,63}$/.test(expectedProjectKey)) {
    throw new Error("invalid lifecycle heading or expected project key");
  }
  const match = /^Execução do projeto:\s*(.+)$/.exec(heading.trim());
  const stateLabel = match?.[1];
  const legacy = [controlState,workObservation,recoveryEligibility].every(value=>value===null);
  let expected;
  if (legacy) {
    if (!Object.hasOwn(LIFECYCLE_COMMANDS, stateLabel)) {
      throw new Error("unknown project execution state: " + String(stateLabel));
    }
    expected = LIFECYCLE_COMMANDS[stateLabel];
  } else {
    if (!Object.hasOwn(RUN_LABELS,workObservation) || !RECOVERY_STATES.has(recoveryEligibility)
        || (controlState!=="running" && !Object.hasOwn(CONTROL_LABELS,controlState))) {
      throw new Error("invalid lifecycle observation contract");
    }
    const observedLabel = controlState==="running"?RUN_LABELS[workObservation]:CONTROL_LABELS[controlState];
    if (stateLabel!==observedLabel) throw new Error("lifecycle worker observation/label mismatch");
    if (controlState!=="running" && recoveryEligibility==="eligible")
      throw new Error("lifecycle recovery cannot be eligible while control is not running");
    expected=controlState==="running"
      ?["pause","stop",...(recoveryEligibility==="eligible"?["restart"]:[])]
      :LIFECYCLE_COMMANDS[observedLabel];
  }
  if (!Array.isArray(forms)) throw new Error("invalid lifecycle forms");
  const actual = forms.map(form => form?.command);
  if (JSON.stringify([...actual].sort()) !== JSON.stringify([...expected].sort())) {
    throw new Error("lifecycle command/state mismatch: " + stateLabel + " => " + JSON.stringify(actual));
  }
  const versions = new Set();
  for (const form of forms) {
    if (form?.projectKey !== expectedProjectKey || !Object.hasOwn(LABELS, form?.command) ||
        typeof form?.label !== "string" || form.label.trim() !== LABELS[form.command] ||
        typeof form?.version !== "string" || !/^(0|[1-9][0-9]*)$/.test(form.version) ||
        !Number.isSafeInteger(Number(form.version)) ||
        typeof form?.commandId !== "string" || form.commandId !== "") {
      throw new Error("invalid project/version/command/idempotency identity");
    }
    versions.add(form.version);
  }
  if (versions.size > 1) throw new Error("inconsistent lifecycle control versions");
  return {
    stateLabel,
    ...(legacy?{}:{controlState,workObservation,recoveryEligibility}),
    availableCommands: [...actual].sort(),
    version: forms[0]?.version ?? null,
    verifiedWithoutMutation: true,
    commandIdAllocatedBeforeSubmit: false,
  };
}
