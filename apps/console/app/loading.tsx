export default function Loading(){
 return <div className="card consoleRouteLoading" role="status" aria-live="polite" aria-atomic="true">
  <strong>Carregando dados da Factory</strong>
  <p className="muted">Aguarde enquanto o Console confirma o estado mais recente do Control Plane.</p>
 </div>;
}
