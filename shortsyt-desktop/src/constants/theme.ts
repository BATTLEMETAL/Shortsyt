/**
 * Flikcut Studio — "The Cut" Design Tokens
 * Mirrored from flikcut.com (k0..k3, volt #C8FF3A, crisp white & mute #A0A7B1)
 */
export const Colors = {
  // Surfaces
  bgPrimary: '#050505',      // k0 — Obsidian black canvas
  bgCard: '#0E0F11',         // k1 — Primary card & sidebar surface
  bgElevated: '#17191C',     // k2 — Elevated surface / table / modal panel
  bgSubtle: '#272A2F',       // k3 — Subtle control / interactive neutral
  bgGlass: 'rgba(14, 15, 17, 0.88)',

  // Accents
  accentVolt: '#C8FF3A',     // Signature Flikcut Volt
  accentVoltHover: '#AEE820',// Pressed / hover volt
  accentGold: '#C8FF3A',     // Alias kept for backwards compatibility
  accentGoldHover: '#AEE820',
  accentBlue: '#5CAEFF',     // Secondary info highlight

  // Text
  textPrimary: '#FFFFFF',    // Crisp white heading / primary copy
  textSecondary: '#A0A7B1',  // Technical mute grey
  textMuted: '#686E78',      // Subtle caption grey
  textInk: '#050505',        // Dark text on volt surfaces

  // Borders & Separators
  borderSubtle: '#272A2F',   // Hairline neutral border
  borderActive: '#C8FF3A',   // Active volt frame

  // Semantic Status
  success: '#C8FF3A',
  successBg: 'rgba(200, 255, 58, 0.12)',
  warning: '#FFB84D',
  warningBg: 'rgba(255, 184, 77, 0.12)',
  error: '#FF5C5C',
  errorBg: 'rgba(255, 92, 92, 0.14)',
};

export const COLORS = Colors;

export const Radius = {
  sm: '2px',
  md: '4px',
  lg: '8px',
  full: '9999px',
};
