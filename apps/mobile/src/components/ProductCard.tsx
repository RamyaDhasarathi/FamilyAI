import React from 'react';
import { ActivityIndicator, Linking, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { ProductCandidate } from '../types';

interface ProductCardProps {
  product: ProductCandidate;
  isSelected?: boolean;
  isCheckingOut?: boolean;
  onSelect?: (product: ProductCandidate) => void;
  onPrepareExecution?: (product: ProductCandidate) => void;
}

export const ProductCard: React.FC<ProductCardProps> = ({
  product,
  isSelected = false,
  isCheckingOut = false,
  onSelect,
  onPrepareExecution,
}) => {
  const isDevData = product.source_type === 'DEVELOPMENT_CATALOGUE';

  const handleOpenUrl = () => {
    if (product.product_url && product.product_url.startsWith('http')) {
      Linking.openURL(product.product_url).catch(() => {});
    }
  };

  const specs = product.specifications_json || {};

  return (
    <View style={[styles.card, isSelected && styles.selectedCard]}>
      {/* Header Badge */}
      <View style={styles.badgeRow}>
        {isDevData ? (
          <View style={styles.devBadge}>
            <Text style={styles.devBadgeText}>🛠️ Development Catalogue</Text>
          </View>
        ) : (
          <View style={styles.realBadge}>
            <Text style={styles.realBadgeText}>✓ Live Marketplace (Amazon)</Text>
          </View>
        )}
        {product.rank ? (
          <View style={styles.rankBadge}>
            <Text style={styles.rankText}>#{product.rank} Match</Text>
          </View>
        ) : null}
      </View>

      {/* Title & Brand */}
      <Text style={styles.title}>{product.title}</Text>
      {product.brand ? <Text style={styles.brand}>Brand: {product.brand}</Text> : null}

      {/* Price */}
      <View style={styles.priceRow}>
        <Text style={styles.price}>
          {product.currency || 'INR'} {product.price_amount?.toLocaleString() || 'N/A'}
        </Text>
        {product.merchant ? (
          <Text style={styles.merchant}>Seller: {product.merchant}</Text>
        ) : null}
      </View>

      {/* Key Details */}
      <View style={styles.detailsContainer}>
        {product.availability ? (
          <Text style={styles.detailText}>
            📦 <Text style={styles.detailLabel}>Availability:</Text> {product.availability}
          </Text>
        ) : null}

        {product.delivery_estimate ? (
          <Text style={styles.detailText}>
            🚚 <Text style={styles.detailLabel}>Delivery:</Text> {product.delivery_estimate}
          </Text>
        ) : null}

        {product.warranty_details ? (
          <Text style={styles.detailText}>
            🛡️ <Text style={styles.detailLabel}>Warranty:</Text> {product.warranty_details}
          </Text>
        ) : null}

        {product.return_details ? (
          <Text style={styles.detailText}>
            ↩️ <Text style={styles.detailLabel}>Returns:</Text> {product.return_details}
          </Text>
        ) : null}
      </View>

      {/* Specifications */}
      {Object.keys(specs).length > 0 ? (
        <View style={styles.specsContainer}>
          <Text style={styles.specsTitle}>Specifications:</Text>
          {Object.entries(specs).slice(0, 4).map(([key, val]) => (
            <Text key={key} style={styles.specItem}>
              • {key}: {String(val)}
            </Text>
          ))}
        </View>
      ) : null}

      {/* Actions */}
      <View style={styles.actionsRow}>
        {onSelect && !isSelected ? (
          <TouchableOpacity
            style={styles.selectButton}
            disabled={isCheckingOut}
            onPress={() => onSelect(product)}
          >
            <Text style={styles.selectButtonText}>Select Option</Text>
          </TouchableOpacity>
        ) : null}

        {isSelected ? (
          <View style={styles.selectedBadge}>
            <Text style={styles.selectedBadgeText}>✓ Selected</Text>
          </View>
        ) : null}

        {onPrepareExecution ? (
          <TouchableOpacity
            style={[styles.prepareButton, isCheckingOut && isSelected && styles.disabledButton]}
            disabled={isCheckingOut}
            onPress={() => onPrepareExecution(product)}
          >
            {isCheckingOut && isSelected ? (
              <View style={styles.checkoutLoadingRow}>
                <ActivityIndicator size="small" color="#ffffff" />
                <Text style={styles.prepareButtonText}>Navigating Amazon...</Text>
              </View>
            ) : (
              <Text style={styles.prepareButtonText}>Proceed to Checkout ➔</Text>
            )}
          </TouchableOpacity>
        ) : null}

        {product.product_url ? (
          <TouchableOpacity style={styles.urlButton} onPress={handleOpenUrl}>
            <Text style={styles.urlButtonText}>View</Text>
          </TouchableOpacity>
        ) : null}
      </View>
    </View>
  );
};

const styles = StyleSheet.create({
  card: {
    backgroundColor: '#ffffff',
    borderRadius: 12,
    padding: 16,
    marginVertical: 8,
    borderWidth: 1,
    borderColor: '#e2e8f0',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.05,
    shadowRadius: 4,
    elevation: 2,
  },
  selectedCard: {
    borderColor: '#4a90d9',
    borderWidth: 2,
    backgroundColor: '#f8fbff',
  },
  badgeRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: 8,
  },
  devBadge: {
    backgroundColor: '#fef3c7',
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 4,
  },
  devBadgeText: {
    color: '#92400e',
    fontSize: 11,
    fontWeight: '600',
  },
  realBadge: {
    backgroundColor: '#d1fae5',
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 4,
  },
  realBadgeText: {
    color: '#065f46',
    fontSize: 11,
    fontWeight: '600',
  },
  rankBadge: {
    backgroundColor: '#ede9fe',
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 4,
  },
  rankText: {
    color: '#5b21b6',
    fontSize: 11,
    fontWeight: '700',
  },
  title: {
    fontSize: 16,
    fontWeight: '700',
    color: '#1a1a2e',
    marginBottom: 4,
  },
  brand: {
    fontSize: 13,
    color: '#64748b',
    marginBottom: 8,
  },
  priceRow: {
    flexDirection: 'row',
    alignItems: 'baseline',
    marginBottom: 10,
  },
  price: {
    fontSize: 18,
    fontWeight: 'bold',
    color: '#0f172a',
    marginRight: 12,
  },
  merchant: {
    fontSize: 12,
    color: '#64748b',
  },
  detailsContainer: {
    backgroundColor: '#f8fafc',
    borderRadius: 8,
    padding: 8,
    marginBottom: 8,
  },
  detailText: {
    fontSize: 12,
    color: '#334155',
    marginBottom: 3,
  },
  detailLabel: {
    fontWeight: '600',
  },
  specsContainer: {
    marginTop: 4,
    marginBottom: 12,
  },
  specsTitle: {
    fontSize: 12,
    fontWeight: '600',
    color: '#475569',
    marginBottom: 4,
  },
  specItem: {
    fontSize: 11,
    color: '#64748b',
    marginLeft: 4,
  },
  actionsRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginTop: 6,
  },
  selectButton: {
    backgroundColor: '#4a90d9',
    paddingVertical: 8,
    paddingHorizontal: 14,
    borderRadius: 6,
  },
  selectButtonText: {
    color: '#ffffff',
    fontSize: 13,
    fontWeight: '600',
  },
  selectedBadge: {
    backgroundColor: '#dbeafe',
    paddingVertical: 8,
    paddingHorizontal: 12,
    borderRadius: 6,
  },
  selectedBadgeText: {
    color: '#1d4ed8',
    fontSize: 13,
    fontWeight: '700',
  },
  prepareButton: {
    backgroundColor: '#10b981',
    paddingVertical: 8,
    paddingHorizontal: 14,
    borderRadius: 6,
  },
  prepareButtonText: {
    color: '#ffffff',
    fontSize: 13,
    fontWeight: '600',
  },
  checkoutLoadingRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  disabledButton: {
    opacity: 0.7,
  },
  urlButton: {
    borderWidth: 1,
    borderColor: '#cbd5e1',
    paddingVertical: 7,
    paddingHorizontal: 10,
    borderRadius: 6,
  },
  urlButtonText: {
    color: '#475569',
    fontSize: 12,
  },
});
