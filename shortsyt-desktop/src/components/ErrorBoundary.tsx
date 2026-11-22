import React, { Component, ErrorInfo, ReactNode } from 'react';
import { AlertTriangle, RotateCcw } from 'lucide-react';

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export default class ErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false,
    error: null,
  };

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('Uncaught error inside ErrorBoundary:', error, errorInfo);
  }

  private handleReset = () => {
    this.setState({ hasError: false, error: null });
    window.location.hash = '#/';
  };

  public render() {
    if (this.state.hasError) {
      return (
        <div className="flex-1 flex flex-col items-center justify-center h-full p-8 text-center text-[#FFFFFF] bg-[#050505]">
          <div className="w-16 h-16 fk-cut-sm bg-[#FF5C5C]/15 border border-[#FF5C5C]/30 flex items-center justify-center mb-4 text-[#FF5C5C]">
            <AlertTriangle className="w-8 h-8" />
          </div>
          <h2 className="text-xl font-extrabold tracking-tight mb-2">Wystąpił problem z widokiem</h2>
          <p className="text-xs text-[#A0A7B1] max-w-md mb-6 leading-relaxed">
            {this.state.error?.message || 'Nieoczekiwany błąd renderowania komponentu.'}
          </p>
          <button
            onClick={this.handleReset}
            className="px-5 py-2.5 fk-btn bg-[#C8FF3A] hover:bg-[#AEE820] text-[#050505] text-xs font-extrabold transition-all flex items-center gap-2"
          >
            <RotateCcw className="w-4 h-4" />
            <span>Wróć do Dashboardu</span>
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}
