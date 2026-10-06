"use client";

import {useState} from "react";

export function PlanningDecisionAnswer({
  name,
  suggestion,
  hint,
}:{
  name:string;
  suggestion?:string|null;
  hint:string;
}){
  const [value,setValue]=useState("");
  const normalizedSuggestion=String(suggestion||"").trim();
  return <label className="planningDecisionAnswer">
    <span>Sua resposta</span>
    <small>{hint}</small>
    {normalizedSuggestion?<div className="planningDecisionSuggestion">
      <div>
        <strong>Sugestão da Factory</strong>
        <p>{normalizedSuggestion}</p>
      </div>
      <button type="button" className="secondary" onClick={()=>setValue(normalizedSuggestion)}>Usar sugestão</button>
    </div>:null}
    <textarea
      name={name}
      required
      rows={4}
      value={value}
      onChange={event=>setValue(event.target.value)}
      placeholder="Escreve aqui a decisão que a Factory deve seguir."
    />
  </label>;
}
