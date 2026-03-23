import { Step3DashboardSection } from "./Step3DashboardSection";
import { Step3FinalListingsSection } from "./Step3FinalListingsSection";
import { Step3PanelTabBar } from "./Step3PanelTabBar";
import { Step3SearchListingsSection } from "./Step3SearchListingsSection";
import { Step3ZoneDetailSection } from "./Step3ZoneDetailSection";
import type { Step3ZonePanelProps } from "./step3Types";

export type { Step3SortedListingRow, Step3ZonePanelProps } from "./step3Types";

export function Step3ZonePanel(props: Step3ZonePanelProps) {
  if (!props.visible) {
    return null;
  }

  const {
    wizardSubStep,
    zoneDetailData,
    zoneInfoSelection,
    selectedZoneUid,
    isDetailingZone,
    zoneListingMessage,
    onDetailZone,
    activePanelTab,
    onActivePanelTabChange,
    streetQuery,
    onStreetQueryChange,
    streetSuggestions,
    selectedStreet,
    selectedStreetType,
    suggestionTypeLabel,
    onStreetSuggestionSelect,
    onZoneListings,
    isListingZone,
    finalizeMessage,
    runId,
    apiBase,
    freshnessBadgeText,
    listingDiffMessage,
    listingSortMode,
    onListingSortModeChange,
    poiCountRadiusM,
    onPoiCountRadiusChange,
    selectedListingsForComparison,
    comparisonExtremes,
    sortedListings,
    onListingCardClick,
    selectedListingKeys,
    newlyAddedListingKeys,
    listingsWithoutCoords,
    parseFiniteNumber,
    formatCurrencyBr,
    finalListings,
    priceRollups,
    monthlyVariation,
    seedTravelTimeMin,
    topPoiCategories
  } = props;

  const zoneDetailBlock = (
    <Step3ZoneDetailSection
      zoneDetailData={zoneDetailData}
      zoneInfoSelection={zoneInfoSelection}
      selectedZoneUid={selectedZoneUid}
      isDetailingZone={isDetailingZone}
      zoneListingMessage={zoneListingMessage}
      onDetailZone={onDetailZone}
    />
  );

  const searchBlock = (
    <Step3SearchListingsSection
      zoneDetailData={zoneDetailData}
      selectedZoneUid={selectedZoneUid}
      isListingZone={isListingZone}
      zoneListingMessage={zoneListingMessage}
      finalizeMessage={finalizeMessage}
      streetQuery={streetQuery}
      onStreetQueryChange={onStreetQueryChange}
      streetSuggestions={streetSuggestions}
      selectedStreet={selectedStreet}
      selectedStreetType={selectedStreetType}
      suggestionTypeLabel={suggestionTypeLabel}
      onStreetSuggestionSelect={onStreetSuggestionSelect}
      onZoneListings={onZoneListings}
    />
  );

  const finalListingsBlock = (
    <Step3FinalListingsSection
      finalizeMessage={finalizeMessage}
      freshnessBadgeText={freshnessBadgeText}
      listingDiffMessage={listingDiffMessage}
      runId={runId}
      apiBase={apiBase}
      finalListings={finalListings}
      listingSortMode={listingSortMode}
      onListingSortModeChange={onListingSortModeChange}
      poiCountRadiusM={poiCountRadiusM}
      onPoiCountRadiusChange={onPoiCountRadiusChange}
      selectedListingsForComparison={selectedListingsForComparison}
      comparisonExtremes={comparisonExtremes}
      sortedListings={sortedListings}
      onListingCardClick={onListingCardClick}
      selectedListingKeys={selectedListingKeys}
      newlyAddedListingKeys={newlyAddedListingKeys}
      listingsWithoutCoords={listingsWithoutCoords}
      parseFiniteNumber={parseFiniteNumber}
      formatCurrencyBr={formatCurrencyBr}
    />
  );

  if (wizardSubStep === 4) {
    return <>{zoneDetailBlock}</>;
  }

  if (wizardSubStep === 5) {
    return <>{searchBlock}</>;
  }

  return (
    <>
      <Step3PanelTabBar activePanelTab={activePanelTab} onActivePanelTabChange={onActivePanelTabChange} />
      {activePanelTab === "listings" ? finalListingsBlock : null}
      {activePanelTab === "dashboard" ? (
        <Step3DashboardSection
          priceRollups={priceRollups}
          monthlyVariation={monthlyVariation}
          seedTravelTimeMin={seedTravelTimeMin}
          finalListings={finalListings}
          zoneDetailData={zoneDetailData}
          topPoiCategories={topPoiCategories}
        />
              ) : null}
    </>
  );
}
