import Combine
import Foundation
import StoreKit

/// StoreKit 2 scaffold for the Day 1 feasibility spike.
/// The $29 app purchase is the App Store price itself; these products are the
/// optional Render subscriptions.
@MainActor
final class StoreManager: ObservableObject {
    static let cpuRenderProduct = "com.ducksuite.app.render.cpu.10h"
    static let gpuRenderProduct = "com.ducksuite.app.render.gpu.10h"

    @Published private(set) var products: [Product] = []
    @Published private(set) var error: String?

    func load() async {
        do {
            products = try await Product.products(for: [
                Self.cpuRenderProduct,
                Self.gpuRenderProduct,
            ])
        } catch {
            self.error = error.localizedDescription
        }
    }

    func purchase(_ product: Product) async {
        do {
            let result = try await product.purchase()
            switch result {
            case .success(let verification):
                switch verification {
                case .verified:
                    break
                case .unverified:
                    self.error = "The App Store could not verify this purchase."
                }
            case .pending:
                break
            case .userCancelled:
                break
            @unknown default:
                break
            }
        } catch {
            self.error = error.localizedDescription
        }
    }

    func restore() async {
        do {
            try await AppStore.sync()
        } catch {
            self.error = error.localizedDescription
        }
    }
}
