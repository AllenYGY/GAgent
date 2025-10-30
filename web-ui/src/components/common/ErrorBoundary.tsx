import React, { Component, ErrorInfo, ReactNode } from 'react';
import { Result, Button } from 'antd';
import { CloseCircleOutlined, ReloadOutlined } from '@ant-design/icons';

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
  errorInfo: ErrorInfo | null;
}

/**
 * React error boundary that captures JavaScript errors in the component tree,
 * logs them, and renders a fallback UI.
 */
const IS_DEV = import.meta.env.DEV;

class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = {
      hasError: false,
      error: null,
      errorInfo: null,
    };
  }

  static getDerivedStateFromError(error: Error): State {
    // Update state so the next render shows the fallback UI
    return {
      hasError: true,
      error,
      errorInfo: null,
    };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    // Log the error details
    console.error('❌ ErrorBoundary caught an error:', error, errorInfo);

    this.setState({
      error,
      errorInfo,
    });

    // TODO: forward to an error-reporting service
    // logErrorToService(error, errorInfo);
  }

  handleReset = () => {
    this.setState({
      hasError: false,
      error: null,
      errorInfo: null,
    });
  };

  handleReload = () => {
    window.location.reload();
  };

  render() {
    if (this.state.hasError) {
      // Respect a custom fallback when provided
      if (this.props.fallback) {
        return this.props.fallback;
      }

      // Default fallback UI
      return (
        <div style={{ padding: '48px 24px', maxWidth: '800px', margin: '0 auto' }}>
          <Result
            status="error"
            icon={<CloseCircleOutlined style={{ color: '#ff4d4f' }} />}
            title="Component rendering failed"
            subTitle="Sorry, something went wrong while rendering this component. Try reloading or contact support."
            extra={[
              <Button type="primary" key="reset" onClick={this.handleReset}>
                Reset component
              </Button>,
              <Button key="reload" icon={<ReloadOutlined />} onClick={this.handleReload}>
                Reload page
              </Button>,
            ]}
          >
            {/* Display error details in development */}
            {IS_DEV && this.state.error && (
              <div
                style={{
                  textAlign: 'left',
                  background: '#fafafa',
                  padding: '16px',
                  borderRadius: '4px',
                  marginTop: '24px',
                }}
              >
                <h4 style={{ color: '#ff4d4f', marginBottom: '12px' }}>Error details (development only)</h4>
                <div
                  style={{
                    fontSize: '12px',
                    fontFamily: 'monospace',
                    color: '#d32f2f',
                    marginBottom: '8px',
                  }}
                >
                  <strong>Message:</strong> {this.state.error.message}
                </div>
                {this.state.error.stack && (
                  <pre
                    style={{
                      fontSize: '11px',
                      fontFamily: 'monospace',
                      color: '#666',
                      background: '#fff',
                      padding: '12px',
                      borderRadius: '4px',
                      overflow: 'auto',
                      maxHeight: '300px',
                      border: '1px solid #d9d9d9',
                    }}
                  >
                    {this.state.error.stack}
                  </pre>
                )}
                {this.state.errorInfo && (
                  <details style={{ marginTop: '12px' }}>
                    <summary style={{ cursor: 'pointer', color: '#1890ff', fontWeight: 'bold' }}>
                      Component stack trace
                    </summary>
                    <pre
                      style={{
                        fontSize: '11px',
                        fontFamily: 'monospace',
                        color: '#666',
                        background: '#fff',
                        padding: '12px',
                        borderRadius: '4px',
                        overflow: 'auto',
                        maxHeight: '300px',
                        border: '1px solid #d9d9d9',
                        marginTop: '8px',
                      }}
                    >
                      {this.state.errorInfo.componentStack}
                    </pre>
                  </details>
                )}
              </div>
            )}
          </Result>
        </div>
      );
    }

    return this.props.children;
  }
}

export default ErrorBoundary;
