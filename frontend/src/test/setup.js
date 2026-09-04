import "@testing-library/jest-dom/vitest";

// jsdom doesn't implement ResizeObserver, which React Flow requires --
// a minimal no-op polyfill is sufficient for rendering in tests.
global.ResizeObserver = class ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
};
