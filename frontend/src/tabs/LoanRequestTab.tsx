import LoanForm from '../forms/LoanForm'

export default function LoanRequestTab() {
  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-2xl mx-auto px-6 py-6">
        <div className="mb-6">
          <h2 className="text-base font-semibold text-[#161616]">Loan Request</h2>
          <p className="mt-1 text-xs text-[#525252]">
            Detail the credit request. This information anchors the underwriting narrative.
          </p>
        </div>
        <LoanForm />
      </div>
    </div>
  )
}
