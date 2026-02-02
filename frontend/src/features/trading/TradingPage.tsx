/**
 * Trading Page
 * Main trading interface with order entry panel
 */

import { Card, Row, Col } from 'antd';
import { OrderEntryPanel } from './components/OrderEntryPanel';

const TradingPage = () => {
  return (
    <div style={{ padding: '24px' }}>
      <Row gutter={[16, 16]}>
        <Col xs={24} lg={12} xl={10}>
          <Card 
            title="Order Entry" 
            variant="borderless"
            style={{ height: '100%' }}
          >
            <OrderEntryPanel />
          </Card>
        </Col>
        
        <Col xs={24} lg={12} xl={14}>
          <Card 
            title="Market Information" 
            variant="borderless"
            style={{ height: '100%', minHeight: '600px' }}
          >
            <div style={{ 
              display: 'flex', 
              alignItems: 'center', 
              justifyContent: 'center',
              height: '100%',
              color: '#999'
            }}>
              <div style={{ textAlign: 'center' }}>
                <p>Market data and charts will appear here</p>
                <p style={{ fontSize: '12px', marginTop: '8px' }}>
                  (To be implemented in future phase)
                </p>
              </div>
            </div>
          </Card>
        </Col>
      </Row>
    </div>
  );
};

export default TradingPage;
