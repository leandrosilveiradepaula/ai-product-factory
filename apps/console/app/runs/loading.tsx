/** Explicit nested loading boundary for real client transitions into /runs. */
export default function RunsLoading(){
 return <div className="card consoleRouteLoading" role="status" aria-live="polite" aria-atomic="true">
  <strong>Carregando execuções</strong>
  <p className="muted">Consultando o estado real do Control Plane. Nenhuma execução está sendo iniciada.</p>
 </div>;
}
