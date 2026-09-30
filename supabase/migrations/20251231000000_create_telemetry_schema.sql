CREATE TABLE public.telemetry_observations (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  observed_at timestamptz NOT NULL,
  work_detected boolean NOT NULL,
  CONSTRAINT telemetry_observations_observed_at_finite CHECK (isfinite(observed_at))
);

CREATE TABLE public.telemetry_work_classes (
  work_class text PRIMARY KEY,
  CONSTRAINT telemetry_work_classes_supported_value CHECK (
    work_class IN (
      'code',
      'configuration',
      'dependency',
      'documentation',
      'infrastructure',
      'test',
      'other'
    )
  )
);

INSERT INTO public.telemetry_work_classes (work_class)
VALUES
  ('code'),
  ('configuration'),
  ('dependency'),
  ('documentation'),
  ('infrastructure'),
  ('test'),
  ('other');

CREATE TABLE public.telemetry_observation_work_classes (
  observation_id bigint NOT NULL
    REFERENCES public.telemetry_observations (id) ON DELETE CASCADE,
  work_class text NOT NULL
    REFERENCES public.telemetry_work_classes (work_class),
  PRIMARY KEY (observation_id, work_class)
);

CREATE INDEX telemetry_observations_observed_at_idx
  ON public.telemetry_observations (observed_at);

CREATE INDEX telemetry_observation_work_classes_work_class_idx
  ON public.telemetry_observation_work_classes (work_class);

CREATE FUNCTION public.validate_telemetry_observation_work_classes()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
  target_observation_id bigint;
  target_work_detected boolean;
BEGIN
  IF TG_TABLE_NAME = 'telemetry_observations' THEN
    target_observation_id := NEW.id;
  ELSE
    target_observation_id := COALESCE(NEW.observation_id, OLD.observation_id);
  END IF;

  SELECT work_detected
    INTO target_work_detected
    FROM public.telemetry_observations
   WHERE id = target_observation_id;

  -- A cascading observation deletion may invoke the association trigger after
  -- the parent row is no longer present.
  IF NOT FOUND THEN
    RETURN NULL;
  END IF;

  IF target_work_detected AND NOT EXISTS (
    SELECT 1
      FROM public.telemetry_observation_work_classes
     WHERE observation_id = target_observation_id
  ) THEN
    RAISE EXCEPTION
      'work-detected telemetry observation % must have at least one work class',
      target_observation_id;
  END IF;

  IF NOT target_work_detected AND EXISTS (
    SELECT 1
      FROM public.telemetry_observation_work_classes
     WHERE observation_id = target_observation_id
  ) THEN
    RAISE EXCEPTION
      'no-work telemetry observation % cannot have work classes',
      target_observation_id;
  END IF;

  RETURN NULL;
END;
$$;

CREATE CONSTRAINT TRIGGER telemetry_observations_work_class_consistency
AFTER INSERT OR UPDATE OF work_detected
ON public.telemetry_observations
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW
EXECUTE FUNCTION public.validate_telemetry_observation_work_classes();

CREATE CONSTRAINT TRIGGER telemetry_observation_work_classes_consistency
AFTER INSERT OR UPDATE OR DELETE
ON public.telemetry_observation_work_classes
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW
EXECUTE FUNCTION public.validate_telemetry_observation_work_classes();
