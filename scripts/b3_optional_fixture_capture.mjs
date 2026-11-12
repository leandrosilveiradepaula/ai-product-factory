/** Isolate bounded intercepted-GET UI states from live authenticated WCAG.
 * A missing synthetic transition is not evidence of a real-world UI failure
 * and cannot certify states. No other errors are swallowed.
 */
import {B3SyntheticTransitionTimeout} from "./verify_block1_b3_live_console_states.mjs";

export async function collectBoundedB3Fixture({observe,save,report}){
  if(typeof observe!=="function"||typeof save!=="function"||typeof report!=="function")
    throw Error("b3_fixture_callbacks_required");
  let witness;
  try{
    witness=await observe();
  }catch(error){
    if(!(error instanceof B3SyntheticTransitionTimeout))throw error;
    // No human-readable page text, operator details or fixture HTTP bodies.
    report({status:"b3_synthetic_ui_transition_not_observed",
      transition:error.transition,
      actualBackendStateCertified:false,fullUserExperienceCertified:false,
      independentCriterionCertified:false,visualAuditPassed:false});
    return null;
  }
  // A real observed positive must be persisted or fail the whole capture.
  await save(witness);
  return witness;
}
