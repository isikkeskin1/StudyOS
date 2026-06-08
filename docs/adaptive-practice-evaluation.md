# Adaptive Practice Evaluation

StudyOS 0.20.0 closes the loop between guided practice, grading, mastery, mistake intelligence, and the next practice decision.

## Evaluation flow

```text
practice question
    -> student answer
    -> deterministic solution-grounded grade
    -> structured mistakes
    -> hint-aware mastery evidence
    -> mastery + mastery history recompute
    -> mistake analytics update
    -> adaptive next-practice decision
```

The evaluation endpoint is:

```text
POST /api/v1/courses/{course_id}/tutor/practice/{practice_id}/evaluate
```

Example payload:

```json
{
  "student_answer": "F = ma, so the force is 10 N.",
  "duration_seconds": 75,
  "generate_next": true
}
```

## Correctness is not a hint penalty

The returned `score` is the grader's estimate of answer correctness. StudyOS does not lower that score merely because a hint was used.

Instead, hint use lowers `mastery_weight`, which controls how strongly the attempt updates topic mastery. This keeps two different questions separate:

- Was the submitted answer correct?
- How strong is this attempt as independent evidence of mastery?

The full solution is stricter: after the solution is revealed, the practice item can no longer be submitted as mastery evidence.

## Adaptive next-practice policy

StudyOS chooses one of four strategies after a scored attempt:

- `reinforce`: weak or heavily hinted performance; stay on the topic and step difficulty down when possible.
- `maintain`: mixed performance; keep the same topic and difficulty.
- `increase_difficulty`: strong unassisted performance; stay on the topic and step difficulty up.
- `reoptimize`: sufficiently strong mastery; release topic selection back to the course-wide weakness optimizer.

Next-item generation is fail-soft. If a provider or source cannot produce the next practice item, the completed evaluation and mastery update remain committed.

## Shared mastery and mistake systems

Practice attempts are first-class evidence alongside diagnostic responses. `recompute_course_mastery()` now aggregates both evidence sources into the same Bayesian mastery state.

Practice mistakes also feed the existing course mistake summary and therefore the study planner's mistake-priority signal. A weak practice answer can consequently change all of:

```text
practice feedback
mastery
mastery history
mistake burden
study-plan priority
next practice selection
```

## Grading limitations

Version 0.20.0 uses the existing deterministic lexical/numeric solution grader for practice evaluation. It is intentionally labelled provisional and stores grader confidence plus evidence coverage. A later provider-backed grading adapter can replace the grader without changing the practice-attempt or mastery contracts.
