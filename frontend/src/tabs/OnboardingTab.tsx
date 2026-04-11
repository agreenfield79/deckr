import BorrowerForm from '../forms/BorrowerForm'

export default function OnboardingTab() {
  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-2xl mx-auto px-6 py-6">
        <div className="mb-6">
          <h2 className="text-base font-semibold text-[#161616]">Borrower Onboarding</h2>
          <p className="mt-1 text-xs text-[#525252]">
            Complete your business profile. This information will be used across your
            underwriting package.
          </p>
        </div>
        <BorrowerForm />
      </div>
    </div>
  )
}
