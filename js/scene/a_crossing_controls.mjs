export function actionSurfaceSignature(actions = []) {
  return JSON.stringify(actions.map(({ subject, kind, choice, label, emphasis }) => [
    subject,
    kind,
    choice,
    label,
    emphasis,
  ]));
}
