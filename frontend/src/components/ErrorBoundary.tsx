/**
 * React error boundary (#1741).
 *
 * Catches render-time errors anywhere in the tree, logs them (which reflows to
 * the backend via the logger), and renders a recoverable fallback instead of a
 * blank screen — closing the "frontend crash is invisible" gap for the alpha
 * closed-beta.
 */

import { Component, type ErrorInfo, type ReactNode } from "react";

import { logger } from "../lib/logger";

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    logger.error(`react error boundary: ${error.message}`, {
      stack: error.stack,
      componentStack: info.componentStack,
    });
  }

  private handleReload = (): void => {
    window.location.reload();
  };

  render(): ReactNode {
    const { error } = this.state;
    if (error) {
      return (
        <div
          className="flex h-screen flex-col items-center justify-center gap-4 bg-red-50 p-8 text-center"
          data-testid="app-error-boundary"
        >
          <h1 className="text-lg font-semibold text-red-700">Something went wrong</h1>
          <p className="max-w-md whitespace-pre-wrap text-sm text-red-600">{error.message}</p>
          <button
            type="button"
            onClick={this.handleReload}
            className="rounded bg-red-600 px-4 py-2 text-sm text-white hover:bg-red-700"
          >
            Reload
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
