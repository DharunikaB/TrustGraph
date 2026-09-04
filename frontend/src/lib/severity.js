/** Central severity -> color/label mapping so every panel agrees visually. */

const LEVEL_STYLES = {
  CRITICAL: {
    text: "text-red-400",
    bg: "bg-red-500/10",
    border: "border-red-500/40",
    dot: "bg-red-500",
  },
  HIGH: {
    text: "text-orange-400",
    bg: "bg-orange-500/10",
    border: "border-orange-500/40",
    dot: "bg-orange-500",
  },
  MEDIUM: {
    text: "text-amber-400",
    bg: "bg-amber-500/10",
    border: "border-amber-500/40",
    dot: "bg-amber-400",
  },
  LOW: {
    text: "text-emerald-400",
    bg: "bg-emerald-500/10",
    border: "border-emerald-500/40",
    dot: "bg-emerald-500",
  },
};

const DEFAULT_STYLE = {
  text: "text-gray-400",
  bg: "bg-gray-500/10",
  border: "border-gray-500/40",
  dot: "bg-gray-500",
};

export function levelStyle(level) {
  return LEVEL_STYLES[level] || DEFAULT_STYLE;
}

const ACTION_STYLES = {
  NO_ACTION: DEFAULT_STYLE,
  MONITOR: LEVEL_STYLES.LOW,
  REVIEW: LEVEL_STYLES.MEDIUM,
  HOLD_FOR_REVIEW: LEVEL_STYLES.HIGH,
  ESCALATE: LEVEL_STYLES.CRITICAL,
};

export function actionStyle(action) {
  return ACTION_STYLES[action] || DEFAULT_STYLE;
}

const STATUS_STYLES = {
  COMPLETED: LEVEL_STYLES.LOW,
  SIMULATED: LEVEL_STYLES.LOW,
  DUPLICATE: LEVEL_STYLES.MEDIUM,
  AI_UNAVAILABLE: DEFAULT_STYLE,
  INVESTIGATION_FAILED: LEVEL_STYLES.HIGH,
  REJECTED: LEVEL_STYLES.HIGH,
  FAILED: LEVEL_STYLES.CRITICAL,
};

export function statusStyle(status) {
  return STATUS_STYLES[status] || DEFAULT_STYLE;
}
